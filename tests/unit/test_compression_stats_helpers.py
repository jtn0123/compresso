#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_compression_stats_helpers.py

    Unit tests for compresso/webserver/helpers/compression_stats.py helper wrappers.
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unittest
class TestGetCompressionSummary:

    @patch('compresso.webserver.helpers.compression_stats.history')
    def test_delegates_to_history(self, mock_history_mod):
        from compresso.webserver.helpers.compression_stats import get_compression_summary
        mock_instance = MagicMock()
        mock_history_mod.History.return_value = mock_instance
        mock_instance.get_library_compression_summary.return_value = {'total_source_size': 100}

        result = get_compression_summary(library_id=5)
        mock_instance.get_library_compression_summary.assert_called_once_with(library_id=5)
        assert result == {'total_source_size': 100}

    @patch('compresso.webserver.helpers.compression_stats.history')
    def test_no_library_id(self, mock_history_mod):
        from compresso.webserver.helpers.compression_stats import get_compression_summary
        mock_instance = MagicMock()
        mock_history_mod.History.return_value = mock_instance
        mock_instance.get_library_compression_summary.return_value = {}

        get_compression_summary()
        mock_instance.get_library_compression_summary.assert_called_once_with(library_id=None)


@pytest.mark.unittest
class TestGetCompressionStatsPaginated:

    @patch('compresso.webserver.helpers.compression_stats.history')
    def test_delegates_with_params(self, mock_history_mod):
        from compresso.webserver.helpers.compression_stats import get_compression_stats_paginated
        mock_instance = MagicMock()
        mock_history_mod.History.return_value = mock_instance
        mock_instance.get_compression_stats_paginated.return_value = {'results': []}

        params = {'start': 5, 'length': 20, 'search_value': 'test', 'library_id': 2, 'order': {'column': 'size', 'dir': 'asc'}}
        result = get_compression_stats_paginated(params)
        mock_instance.get_compression_stats_paginated.assert_called_once_with(
            start=5, length=20, search_value='test', library_id=2, order={'column': 'size', 'dir': 'asc'}
        )

    @patch('compresso.webserver.helpers.compression_stats.history')
    def test_defaults_for_missing_params(self, mock_history_mod):
        from compresso.webserver.helpers.compression_stats import get_compression_stats_paginated
        mock_instance = MagicMock()
        mock_history_mod.History.return_value = mock_instance
        mock_instance.get_compression_stats_paginated.return_value = {}

        get_compression_stats_paginated({})
        mock_instance.get_compression_stats_paginated.assert_called_once_with(
            start=0, length=10, search_value='', library_id=None, order=None
        )


@pytest.mark.unittest
class TestDistributionWrappers:

    @patch('compresso.webserver.helpers.compression_stats.history')
    def test_codec_distribution_delegates(self, mock_history_mod):
        from compresso.webserver.helpers.compression_stats import get_codec_distribution
        mock_instance = MagicMock()
        mock_history_mod.History.return_value = mock_instance
        mock_instance.get_codec_distribution.return_value = [{'codec': 'hevc', 'count': 5}]

        result = get_codec_distribution(library_id=1)
        mock_instance.get_codec_distribution.assert_called_once_with(library_id=1)

    @patch('compresso.webserver.helpers.compression_stats.history')
    def test_resolution_distribution_delegates(self, mock_history_mod):
        from compresso.webserver.helpers.compression_stats import get_resolution_distribution
        mock_instance = MagicMock()
        mock_history_mod.History.return_value = mock_instance

        get_resolution_distribution(library_id=2)
        mock_instance.get_resolution_distribution.assert_called_once_with(library_id=2)

    @patch('compresso.webserver.helpers.compression_stats.history')
    def test_container_distribution_delegates(self, mock_history_mod):
        from compresso.webserver.helpers.compression_stats import get_container_distribution
        mock_instance = MagicMock()
        mock_history_mod.History.return_value = mock_instance

        get_container_distribution(library_id=3)
        mock_instance.get_container_distribution.assert_called_once_with(library_id=3)

    @patch('compresso.webserver.helpers.compression_stats.history')
    def test_space_saved_over_time_delegates(self, mock_history_mod):
        from compresso.webserver.helpers.compression_stats import get_space_saved_over_time
        mock_instance = MagicMock()
        mock_history_mod.History.return_value = mock_instance

        get_space_saved_over_time(library_id=1, interval='week')
        mock_instance.get_space_saved_over_time.assert_called_once_with(library_id=1, interval='week')


@pytest.mark.unittest
class TestGetPendingEstimate:

    @patch('compresso.webserver.helpers.compression_stats.history')
    def test_returns_correct_structure(self, mock_history_mod):
        from compresso.webserver.helpers.compression_stats import get_pending_estimate
        mock_instance = MagicMock()
        mock_history_mod.History.return_value = mock_instance
        mock_instance.get_library_compression_summary.return_value = {'avg_ratio': 0.5}

        MockTasks = MagicMock()
        mock_query = MagicMock()
        MockTasks.select.return_value.where.return_value = mock_query
        mock_query.count.return_value = 3
        mock_query.__iter__ = MagicMock(return_value=iter([
            MagicMock(source_size=1000),
            MagicMock(source_size=2000),
            MagicMock(source_size=3000),
        ]))

        with patch('compresso.libs.unmodels.Tasks', MockTasks):
            result = get_pending_estimate()
        assert result['pending_count'] == 3
        assert result['total_pending_size'] == 6000
        assert result['estimated_output_size'] == 3000
        assert result['estimated_savings'] == 3000
        assert result['avg_ratio_used'] == 0.5

    @patch('compresso.webserver.helpers.compression_stats.history')
    def test_zero_pending_returns_zeros(self, mock_history_mod):
        from compresso.webserver.helpers.compression_stats import get_pending_estimate
        mock_instance = MagicMock()
        mock_history_mod.History.return_value = mock_instance
        mock_instance.get_library_compression_summary.return_value = {'avg_ratio': 0.5}

        MockTasks = MagicMock()
        mock_query = MagicMock()
        MockTasks.select.return_value.where.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.__iter__ = MagicMock(return_value=iter([]))

        with patch('compresso.libs.unmodels.Tasks', MockTasks):
            result = get_pending_estimate()
        assert result['pending_count'] == 0
        assert result['total_pending_size'] == 0
        assert result['estimated_savings'] == 0

    @patch('compresso.webserver.helpers.compression_stats.history')
    def test_avg_ratio_zero_falls_back_to_one(self, mock_history_mod):
        from compresso.webserver.helpers.compression_stats import get_pending_estimate
        mock_instance = MagicMock()
        mock_history_mod.History.return_value = mock_instance
        mock_instance.get_library_compression_summary.return_value = {'avg_ratio': 0}

        MockTasks = MagicMock()
        mock_query = MagicMock()
        MockTasks.select.return_value.where.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.__iter__ = MagicMock(return_value=iter([MagicMock(source_size=1000)]))

        with patch('compresso.libs.unmodels.Tasks', MockTasks):
            result = get_pending_estimate()
        assert result['avg_ratio_used'] == 1.0
        assert result['estimated_savings'] == 0

    @patch('compresso.webserver.helpers.compression_stats.history')
    def test_negative_ratio_falls_back_to_one(self, mock_history_mod):
        from compresso.webserver.helpers.compression_stats import get_pending_estimate
        mock_instance = MagicMock()
        mock_history_mod.History.return_value = mock_instance
        mock_instance.get_library_compression_summary.return_value = {'avg_ratio': -0.5}

        MockTasks = MagicMock()
        mock_query = MagicMock()
        MockTasks.select.return_value.where.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.__iter__ = MagicMock(return_value=iter([MagicMock(source_size=1000)]))

        with patch('compresso.libs.unmodels.Tasks', MockTasks):
            result = get_pending_estimate()
        assert result['avg_ratio_used'] == 1.0

    @patch('compresso.webserver.helpers.compression_stats.history')
    def test_db_exception_returns_zero_gracefully(self, mock_history_mod):
        from compresso.webserver.helpers.compression_stats import get_pending_estimate
        mock_instance = MagicMock()
        mock_history_mod.History.return_value = mock_instance
        mock_instance.get_library_compression_summary.return_value = {'avg_ratio': 0.5}

        MockTasks = MagicMock()
        MockTasks.select.return_value.where.return_value.count.side_effect = Exception("DB error")

        with patch('compresso.libs.unmodels.Tasks', MockTasks):
            result = get_pending_estimate()
        assert result['pending_count'] == 0
        assert result['total_pending_size'] == 0
