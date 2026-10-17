"""Services modules package for RTK CRM.

This package contains modular domain services:
- common: datetime helpers, json serializer, SQLAlchemy session event listeners
- rbac: permissions, authz epoch, scoping and access control
- idempotency: command reservation and deduplication
- interactions: CRUD, state transitions, CAS, catalogs, workflow migrations
- reports: temporal report snapshots, activity, created report, background jobs
"""
