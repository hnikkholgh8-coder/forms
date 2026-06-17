#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
from typing import Dict, List, Tuple, Any
from difflib import SequenceMatcher
from schemas_contract import UserSchema, AssetSchema
from security.audit_logger import exir_boundary_tracer

logger = logging.getLogger("exir_architecture_tracer")

class LookupMatch:
    def __init__(self, label: str, identifier: Any, score: float):
        self.label = label
        self.identifier = identifier
        self.score = score  # 0.0 to 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "identifier": str(self.identifier),
            "score": round(self.score, 4)
        }

class EngineLookup:
    """
    Fast in-memory fuzzy text lookup engine.
    Maintains caches of users and assets with sub-millisecond query response times.
    """

    def __init__(self):
        self.users_cache: Dict[str, UserSchema] = {}
        self.assets_cache: Dict[str, AssetSchema] = {}
        self.users_by_name: Dict[str, str] = {}  # Name -> User ID for fast reverse lookup

    def load_users(self, users: List[UserSchema]) -> None:
        """Load users into the in-memory cache."""
        for user in users:
            self.users_cache[str(user.id)] = user
            # Normalize name for fuzzy matching
            self.users_by_name[user.full_name.lower()] = str(user.id)

    def load_assets(self, assets: List[AssetSchema]) -> None:
        """Load assets into the in-memory cache."""
        for asset in assets:
            self.assets_cache[str(asset.id)] = asset

    @staticmethod
    def _similarity_score(a: str, b: str) -> float:
        """Calculate Levenshtein-based similarity score between two strings."""
        a, b = a.lower().strip(), b.lower().strip()
        ratio = SequenceMatcher(None, a, b).ratio()
        return ratio

    @exir_boundary_tracer
    async def search_users(self, query: str, threshold: float = 0.6) -> List[LookupMatch]:
        """
        Fuzzy search for users by name or username.
        """
        if not query or len(query.strip()) < 2:
            return []
        
        results = []
        normalized_query = query.lower().strip()
        
        for user_id, user in self.users_cache.items():
            # Check full name
            name_score = self._similarity_score(normalized_query, user.full_name)
            if name_score >= threshold:
                results.append(LookupMatch(user.full_name, user_id, name_score))
            
            # Check username
            username_score = self._similarity_score(normalized_query, user.username)
            if username_score >= threshold and username_score > name_score:
                results.append(LookupMatch(f"{user.full_name} (@{user.username})", user_id, username_score))
        
        # Sort by score descending
        results.sort(key=lambda m: m.score, reverse=True)
        return results[:10]  # Return top 10 matches

    @exir_boundary_tracer
    async def search_assets(self, query: str, threshold: float = 0.6) -> List[LookupMatch]:
        """
        Fuzzy search for assets by code or name.
        """
        if not query or len(query.strip()) < 2:
            return []
        
        results = []
        normalized_query = query.lower().strip()
        
        for asset_id, asset in self.assets_cache.items():
            # Check asset code
            code_score = self._similarity_score(normalized_query, asset.asset_code)
            if code_score >= threshold:
                results.append(LookupMatch(f"{asset.asset_code} - {asset.asset_name}", asset_id, code_score))
            
            # Check asset name
            name_score = self._similarity_score(normalized_query, asset.asset_name)
            if name_score >= threshold and name_score > code_score:
                results.append(LookupMatch(asset.asset_name, asset_id, name_score))
        
        # Sort by score descending
        results.sort(key=lambda m: m.score, reverse=True)
        return results[:10]  # Return top 10 matches

# Global Singleton Instance
engine_lookup = EngineLookup()
