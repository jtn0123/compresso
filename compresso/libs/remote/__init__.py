"""Multi-machine link support.

Everything Compresso needs to hand work to another installation and get the
result back: the link registry and its credentials (:mod:`installation_link`),
claiming and renewing remote task leases (:mod:`remote_task_lease`), driving a
task through a remote worker (:mod:`remote_task_manager`), and moving the media
itself with resumable chunked transfers (:mod:`resumable_transfer`).

Import the modules directly; this package intentionally re-exports nothing so
the dependency each caller takes stays visible at the import site.
"""
