from __future__ import annotations

import pytest


class _FakeDocSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self, collection_store: dict, doc_id: str):
        self._store = collection_store
        self._doc_id = doc_id

    def get(self):
        return _FakeDocSnapshot(self._store.get(self._doc_id))

    def set(self, data):
        self._store[self._doc_id] = data


class _FakeCollectionRef:
    def __init__(self, store: dict):
        self._store = store

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self._store, doc_id)


class FakeFirestoreClient:
    """In-memory stand-in for google.cloud.firestore.Client — enough surface
    (collection().document().get()/.set()) for jh_clio_lib's usage."""

    def __init__(self, project=None):
        self.project = project
        self._collections: dict[str, dict] = {}

    def collection(self, name: str) -> _FakeCollectionRef:
        self._collections.setdefault(name, {})
        return _FakeCollectionRef(self._collections[name])

    def seed(self, collection: str, doc_id: str, data: dict) -> None:
        self._collections.setdefault(collection, {})[doc_id] = data


@pytest.fixture
def fake_firestore(monkeypatch):
    from google.cloud import firestore as firestore_module

    instance = FakeFirestoreClient()
    monkeypatch.setattr(firestore_module, "Client", lambda project=None: instance)
    return instance
