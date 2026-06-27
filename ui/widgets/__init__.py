#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CustomTkinter 기반 대시보드 위젯들
"""

from .ai_learning_widget import AILearningWidget
from .ai_report_widget import AIReportWidget
from .ai_assistant_widget import AIAssistantWidget
from .life_finance_widget import LifeFinanceWidget

__all__ = [
    'AILearningWidget',
    'AIReportWidget', 
    'AIAssistantWidget',
    'LifeFinanceWidget',
]
