"""Useful logging filters.
"""
import logging

__all__ = "IgnoreHealthCheckerFilter",


class IgnoreHealthCheckerFilter(logging.Filter):
    user_agent = 'ELB-HealthChecker/2.0'

    def __init__(self, user_agent=None):
        super().__init__()
        if user_agent:
            self.user_agent = user_agent

    def filter(self, record):
        return record.getMessage().find(self.user_agent) == -1
