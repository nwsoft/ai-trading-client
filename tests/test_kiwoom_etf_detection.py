#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
키움증권 ETF 판별 로직 테스트
ETF 코드 범위 기반 판별이 정확한지 검증
"""

import unittest
import sys
import os

# 프로젝트 루트 추가
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from trading.exchanges.adapters.kiwoom_stock_adapter import KiwoomStockAdapter


class TestKiwoomETFDetection(unittest.TestCase):
    """키움증권 ETF 판별 로직 테스트"""
    
    def setUp(self):
        """테스트 셋업"""
        self.adapter = KiwoomStockAdapter(
            user_id="test_user",
            password="test_pwd",
            cert_password="test_cert",
            account_no="test_account"
        )
    
    # ===== ETF 판별 테스트 =====
    
    def test_kodex_etf_detection(self):
        """KODEX/KINDEX 등 일반 ETF 판별"""
        # 69500번대는 ETF
        self.assertTrue(self.adapter.is_etf("069500"), "KODEX KOSPI 200은 ETF여야 함")
        self.assertTrue(self.adapter.is_etf("069570"), "KODEX 변동성은 ETF여야 함")
        self.assertTrue(self.adapter.is_etf("069590"), "KINDEX")
    
    def test_theme_etf_detection(self):
        """테마 ETF 판별 (111000-111999)"""
        self.assertTrue(self.adapter.is_etf("111150"), "테마 ETF 예시")
        self.assertTrue(self.adapter.is_etf("111620"), "테마 ETF 예시")
    
    def test_overseas_etf_detection(self):
        """해외 ETF 판별 (122000-122999)"""
        self.assertTrue(self.adapter.is_etf("122630"), "TIGER 미국나스닥100")
        self.assertTrue(self.adapter.is_etf("122320"), "해외 ETF")
    
    def test_leverage_inverse_etf_detection(self):
        """레버리지/인버스 ETF 판별 (143000-143999)"""
        self.assertTrue(self.adapter.is_etf("143310"), "레버리지 ETF")
        self.assertTrue(self.adapter.is_etf("143320"), "인버스 ETF")
    
    def test_bond_etf_detection(self):
        """채권 ETF 판별 (261000-261999)"""
        self.assertTrue(self.adapter.is_etf("261130"), "채권 ETF")
        self.assertTrue(self.adapter.is_etf("261310"), "채권 ETF")
    
    def test_commodity_etf_detection(self):
        """커머디티 ETF 판별 (292000-292999)"""
        self.assertTrue(self.adapter.is_etf("292000"), "커머디티 ETF")
        self.assertTrue(self.adapter.is_etf("292400"), "커머디티 ETF")
    
    def test_general_etf_range_102000_to_102999(self):
        """일반 ETF 범위 (102000-102999)"""
        self.assertTrue(self.adapter.is_etf("102000"), "ETF 범위 최소값")
        self.assertTrue(self.adapter.is_etf("102999"), "ETF 범위 최대값")
        self.assertTrue(self.adapter.is_etf("102630"), "일반 ETF 예시")
    
    # ===== 주식 (비-ETF) 판별 테스트 =====
    
    def test_stock_not_detected_as_etf(self):
        """일반 주식은 ETF로 판별되지 않음"""
        # 대형주
        self.assertFalse(self.adapter.is_etf("005930"), "삼성전자는 주식")
        self.assertFalse(self.adapter.is_etf("000660"), "SK하이닉스는 주식")
        self.assertFalse(self.adapter.is_etf("051910"), "LG화학은 주식")
        
        # 중형주
        self.assertFalse(self.adapter.is_etf("035720"), "카카오는 주식")
        self.assertFalse(self.adapter.is_etf("068270"), "셀트리온은 주식")
        
        # 소형주
        self.assertFalse(self.adapter.is_etf("999999"), "임의 6자리는 주식")
    
    def test_etf_boundary_values(self):
        """ETF 범위 경계값 테스트"""
        # 69500 범위 (단 1개)
        self.assertTrue(self.adapter.is_etf("069500"))
        self.assertFalse(self.adapter.is_etf("069499"))
        self.assertFalse(self.adapter.is_etf("069600"))
        
        # 102000-102999
        self.assertTrue(self.adapter.is_etf("102000"))
        self.assertTrue(self.adapter.is_etf("102999"))
        self.assertFalse(self.adapter.is_etf("101999"))
        self.assertFalse(self.adapter.is_etf("103000"))
    
    # ===== 예외 처리 테스트 =====
    
    def test_invalid_input_handling(self):
        """잘못된 입력 처리"""
        # 숫자가 아닌 입력
        self.assertFalse(self.adapter.is_etf("ABC123"), "문자 포함 코드")
        self.assertFalse(self.adapter.is_etf(""), "빈 문자열")
        self.assertFalse(self.adapter.is_etf("   "), "공백")
        
        # None
        self.assertFalse(self.adapter.is_etf(None), "None 입력")  # type: ignore
    
    def test_numeric_input_handling(self):
        """숫자 입력 처리"""
        # 정수로 직접 입력 (불가)
        # 하지만 str로 변환되므로 동작해야 함
        self.assertTrue(self.adapter.is_etf(str(69500)), "정수 입력")
    
    # ===== 추가 테스트 =====
    
    def test_etf_range_coverage(self):
        """모든 ETF 범위 커버리지 확인"""
        etf_ranges = [
            (69500, 69599, "KODEX/KINDEX"),
            (102000, 102999, "일반 ETF"),
            (111000, 111999, "테마 ETF"),
            (122000, 122999, "해외 ETF"),
            (143000, 143999, "레버리지/인버스"),
            (261000, 261999, "채권 ETF"),
            (292000, 292999, "커머디티 ETF"),
        ]
        
        for start, end, desc in etf_ranges:
            # 범위 시작값
            self.assertTrue(self.adapter.is_etf(str(start)), 
                          f"{desc}: 시작값 {start} 판별 실패")
            
            # 범위 중간값
            mid = (start + end) // 2
            self.assertTrue(self.adapter.is_etf(str(mid)), 
                          f"{desc}: 중간값 {mid} 판별 실패")
            
            # 범위 끝값
            self.assertTrue(self.adapter.is_etf(str(end)), 
                          f"{desc}: 끝값 {end} 판별 실패")
    
    def test_stock_range_coverage(self):
        """주식 코드 범위가 ETF로 판별되지 않음"""
        stock_ranges = [
            (1000, 9999, "KOSDAQ 소형주"),
            (10000, 50000, "KOSPI 중형주"),
            (50000, 69499, "KOSPI 대형주~ETF 앞"),
        ]
        
        for start, end, desc in stock_ranges:
            sample = start + (end - start) // 2
            self.assertFalse(self.adapter.is_etf(str(sample)), 
                           f"{desc}: {sample}가 ETF로 잘못 판별됨")


class TestETFDetectionIntegration(unittest.TestCase):
    """ETF 판별 통합 테스트"""
    
    def setUp(self):
        self.adapter = KiwoomStockAdapter(
            user_id="test", password="test", cert_password="test"
        )
    
    def test_batch_etf_detection(self):
        """여러 종목 일괄 판별"""
        test_cases = [
            # (코드, 예상값, 설명)
            ("069500", True, "KODEX KOSPI 200"),
            ("005930", False, "삼성전자"),
            ("122630", True, "TIGER 미국나스닥100"),
            ("000660", False, "SK하이닉스"),
            ("261130", True, "채권 ETF"),
            ("999999", False, "임의 코드"),
        ]
        
        for code, is_etf_expected, desc in test_cases:
            result = self.adapter.is_etf(code)
            self.assertEqual(result, is_etf_expected, 
                           f"{desc} ({code}): 예상 {is_etf_expected}, 실제 {result}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
