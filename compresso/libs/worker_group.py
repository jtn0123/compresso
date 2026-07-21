#!/usr/bin/env python3

"""
compresso.worker_group.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     18 Apr 2022, (4:08 PM)

Copyright:
       Copyright (C) Josh Sunnex - All Rights Reserved

       Permission is hereby granted, free of charge, to any person obtaining a copy
       of this software and associated documentation files (the "Software"), to deal
       in the Software without restriction, including without limitation the rights
       to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
       copies of the Software, and to permit persons to whom the Software is
       furnished to do so, subject to the following conditions:

       The above copyright notice and this permission notice shall be included in all
       copies or substantial portions of the Software.

       THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
       EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
       MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
       IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
       DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
       OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
       OR OTHER DEALINGS IN THE SOFTWARE.

"""

import random
from collections.abc import Mapping, Sequence
from typing import TypedDict

from compresso.libs import narrowing
from compresso.libs.peewee_types import execute_count, execute_write
from compresso.libs.unmodels.tags import Tags
from compresso.libs.unmodels.workergroups import WorkerGroups
from compresso.libs.unmodels.workerschedules import WorkerSchedules


class WorkerScheduleConfig(TypedDict):
    repetition: str
    schedule_task: str
    schedule_time: str
    schedule_worker_count: int | None


class WorkerGroupConfig(TypedDict):
    id: int
    locked: bool
    name: str
    number_of_workers: int
    worker_type: str
    tags: list[str]
    worker_event_schedules: list[WorkerScheduleConfig]


def generate_random_worker_group_name() -> str:
    names = [
        "Altoa",
        "Anje",
        "Anji",
        "Azibo",
        "Azra",
        "Bajin",
        "Baliaja",
        "Benni",
        "Bie",
        "Ditid",
        "Ecia",
        "Ejie",
        "Ekon",
        "Equinus",
        "Erasto",
        "Fefeya",
        "Gamjee",
        "Gilta",
        "Girisha",
        "Haijen",
        "Hakalai",
        "Halasuwa",
        "Hamedi",
        "Hokajin",
        "Hokima",
        "Hyptu",
        "Ithra",
        "Jaryaya",
        "Javinda",
        "Javyn",
        "Jijel",
        "Jinjin",
        "Jiranty",
        "Jumoke",
        "Kaijin",
        "Kanjin",
        "Khuwei",
        "Kina",
        "Lakjin",
        "Makas",
        "Malak",
        "Meimei",
        "Melkree",
        "Napokue",
        "Nelina",
        "Nepita",
        "Nuenvan",
        "Prerrahar",
        "Pujati",
        "Rakash",
        "Reji",
        "Renji",
        "Rhazin",
        "Ronjaty",
        "Rujabu",
        "Saonji",
        "Shadrala",
        "Shengis",
        "Suja",
        "Suli",
        "Suliya",
        "Talisa",
        "Tanjin",
        "Tayo",
        "Tazingo",
        "Tedar",
        "Teshi",
        "Tirezi",
        "Trezzahn",
        "Trolgar",
        "Ttarmek",
        "Ugoki",
        "Valja",
        "Vekuzz",
        "Venjo",
        "Venmara",
        "Vinji",
        "Voyambi",
        "Vujii",
        "Vuzashi",
        "Wanjin",
        "Yaci",
        "Yamike",
        "Yavo",
        "Yera",
        "Yeree",
        "Yetu",
        "Yishi",
        "Yuhai",
        "Zaejin",
        "Zalma",
        "Zea",
        "Zelaji",
        "Zelea",
        "Ziataaman",
        "Ziataima",
        "Ziatakraa",
        "Zola",
        "Zoljin",
        "Zoti",
        "Zujia",
        "Zulabar",
        "Zulja",
        "Zuljah",
        "Zulkis",
        "Zulraja",
        "Zulrajas",
        "Zulwatha",
        "Zulyafi",
        "Zunabar",
        "Zyra",
    ]
    return random.choice(names)  # noqa: S311 — not used for security/crypto


class WorkerGroup:
    """
    WorkerGroup

    Contains all data pertaining to a worker group

    """

    def __init__(self, group_id: int) -> None:
        # Ensure worker group ID is not 0
        if group_id < 1:
            raise Exception("Worker group ID cannot be less than 1")
        model = WorkerGroups.get_or_none(id=group_id)
        if model is None:
            raise Exception(f"Unable to fetch Worker group  with ID {group_id}")
        self.model = model

    @staticmethod
    def random_name() -> str:
        return generate_random_worker_group_name()

    @staticmethod
    def get_all_worker_groups() -> list[WorkerGroupConfig]:
        """
        Return a list of all worker groups

        :return:
        """
        # Fetch all worker groups from DB
        configured_worker_groups = WorkerGroups.select()

        if not configured_worker_groups:
            # v2.0: no legacy top-level number_of_workers / worker_event_schedules
            # to migrate from. New installs start with a single default
            # worker group; the user configures workers through worker
            # groups directly.
            default_worker_group: WorkerGroupConfig = {
                "id": 1,
                "locked": False,
                "name": generate_random_worker_group_name(),
                "number_of_workers": 0,
                "worker_type": "cpu",
                "tags": [],
                "worker_event_schedules": [],
            }
            WorkerGroup.create(default_worker_group)
            return [default_worker_group]

        # Loop over results
        worker_groups: list[WorkerGroupConfig] = []
        for group in configured_worker_groups:
            group_config: WorkerGroupConfig = {
                "id": group.id,
                "locked": group.locked,
                "name": group.name,
                "number_of_workers": group.number_of_workers,
                "worker_type": group.worker_type,
                "worker_event_schedules": [],
                "tags": [],
            }
            # Append tags
            for tag in group.tags.order_by(Tags.name):
                group_config["tags"].append(tag.name)
            # Append worker_event_schedules
            schedules = WorkerSchedules.select().where(WorkerSchedules.worker_group_id == group.id)
            for event_schedule in schedules:
                group_config["worker_event_schedules"].append(
                    {
                        "repetition": event_schedule.repetition,
                        "schedule_task": event_schedule.schedule_task,
                        "schedule_time": event_schedule.schedule_time,
                        "schedule_worker_count": event_schedule.schedule_worker_count,
                    }
                )

            worker_groups.append(group_config)

        # Return the list of worker groups
        return worker_groups

    @staticmethod
    def create(data: Mapping[str, object]) -> None:
        """
        Create a new library

        :param data:
        :return:
        """
        name = data.get("name")
        if not isinstance(name, str) or not name:
            name = generate_random_worker_group_name()

        worker_group_data: dict[str, object] = {
            "locked": bool(data.get("locked", False)),
            "name": name,
            "number_of_workers": narrowing.coerce_int(data.get("number_of_workers")),
            "worker_type": str(data.get("worker_type", "cpu")),
        }
        worker_group_id = WorkerGroups.create(**worker_group_data)

        # Fetch worker group
        worker_group = WorkerGroup(int(worker_group_id.id))

        # Set lists
        tags = data.get("tags", [])
        worker_group.set_tags(
            [tag for tag in tags if isinstance(tag, str)]
            if isinstance(tags, Sequence) and not isinstance(tags, (str, bytes))
            else []
        )
        schedules = data.get("worker_event_schedules", [])
        worker_group.set_worker_event_schedules(
            [schedule for schedule in schedules if isinstance(schedule, Mapping)]
            if isinstance(schedules, Sequence) and not isinstance(schedules, (str, bytes))
            else []
        )

    @staticmethod
    def create_schedules(worker_group_id: int, worker_event_schedules: Sequence[Mapping[str, object]]) -> None:
        for worker_event_schedule in worker_event_schedules:
            worker_event_schedule_data = {
                "worker_group_id": worker_group_id,
                "repetition": worker_event_schedule.get("repetition"),
                "schedule_task": worker_event_schedule.get("schedule_task"),
                "schedule_time": worker_event_schedule.get("schedule_time"),
                "schedule_worker_count": worker_event_schedule.get("schedule_worker_count"),
            }
            WorkerSchedules.create(**worker_event_schedule_data)

    def __remove_schedules(self) -> int:
        """
        Remove all schedules

        :return:
        """
        query = WorkerSchedules.delete()
        query = query.where(WorkerSchedules.worker_group_id == self.model.id)
        return execute_count(query)

    def get_id(self) -> int:
        return int(self.model.id)

    def get_name(self) -> str:
        return str(self.model.name)

    def set_name(self, value: str) -> None:
        self.model.name = value

    def get_locked(self) -> bool:
        return bool(self.model.locked)

    def set_locked(self, value: bool) -> None:
        self.model.locked = value

    def get_number_of_workers(self) -> int:
        return int(self.model.number_of_workers)

    def set_number_of_workers(self, value: int) -> None:
        self.model.number_of_workers = value

    def get_worker_type(self) -> str:
        """
        Returns the worker type ('cpu' or 'gpu') for this group.

        Note: This is currently an organizational/display label only.
        Task routing is determined by tags, not worker_type.
        Future versions may use this for hardware-aware scheduling.
        """
        return str(self.model.worker_type)

    def set_worker_type(self, value: str) -> None:
        if value not in ("cpu", "gpu"):
            raise ValueError("worker_type must be 'cpu' or 'gpu'")
        self.model.worker_type = value

    def get_tags(self) -> list[str]:
        return_value: list[str] = []
        for tag in self.model.tags.order_by(Tags.name):
            return_value.append(tag.name)
        return return_value

    def set_tags(self, value: Sequence[str]) -> None:
        # Create any missing tags
        for tag_name in value:
            # Do not update any current tags with on_conflict_replace() as this will also change their IDs
            # Instead, just ignore them
            execute_write(Tags.insert(name=tag_name).on_conflict_ignore())
        # Create a SELECT query for all tags with the listed names
        tags_select_query = Tags.select().where(Tags.name.in_(value))
        # Clear out the current linking table of tags linked to this library
        # Add new links for each tag that was fetched matching the provided names
        self.model.tags.add(tags_select_query, clear_existing=True)

    def get_worker_event_schedules(self) -> list[WorkerScheduleConfig]:
        return_value: list[WorkerScheduleConfig] = []
        schedules = WorkerSchedules.select().where(WorkerSchedules.worker_group_id == self.model.id)
        for event_schedule in schedules:
            return_value.append(
                {
                    "repetition": event_schedule.repetition,
                    "schedule_task": event_schedule.schedule_task,
                    "schedule_time": event_schedule.schedule_time,
                    "schedule_worker_count": event_schedule.schedule_worker_count,
                }
            )
        return return_value

    def set_worker_event_schedules(self, value: Sequence[Mapping[str, object]]) -> None:
        # Remove all schedules
        self.__remove_schedules()
        # Save the event schedules
        if value:
            WorkerGroup.create_schedules(self.model.id, value)

    def save(self) -> int:
        """
        Save the data for this library

        :return:
        """
        # Ensure a name is actually set
        if not self.get_name():
            self.set_name(generate_random_worker_group_name())

        # Save changes made to model
        return int(self.model.save())

    def delete(self) -> int:
        """
        Delete the current library

        :return:
        """
        # Ensure we are not trying to delete a locked library
        if self.get_locked():
            raise Exception("Unable to remove a locked library")

        # Remove all schedules
        self.__remove_schedules()

        # Remove the library entry
        return int(self.model.delete_instance(recursive=True))
