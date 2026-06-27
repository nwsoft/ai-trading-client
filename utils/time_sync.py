#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
시간 동기화 유틸리티
바이낸스 API는 시간 동기화에 매우 민감하므로 시작 시 자동 동기화
"""

import os
import sys
import subprocess
import platform
from datetime import datetime, timezone
import time


def sync_windows_time(force=False):
    """Windows 시간 동기화 강제 실행"""
    try:
        if platform.system() != 'Windows':
            print("⚠️ Windows가 아닌 환경에서는 시간 동기화를 지원하지 않습니다.")
            return False

        print("🕐 Windows 시간 동기화 시작...")

        # 1. 시간 서비스 시작
        subprocess.run(['net', 'start', 'w32time'],
                      capture_output=True,
                      text=True,
                      creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)

        # 2. 시간 서버 재설정 (time.windows.com 사용)
        subprocess.run(['w32tm', '/config', '/manualpeerlist:time.windows.com', '/syncfromflags:manual', '/reliable:yes', '/update'],
                      capture_output=True,
                      text=True,
                      creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)

        # 3. 즉시 동기화 실행
        result = subprocess.run(['w32tm', '/resync', '/force'],
                               capture_output=True,
                               text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)

        if result.returncode == 0:
            print("✅ Windows 시간 동기화 완료")
            return True
        else:
            print(f"⚠️ 시간 동기화 실패: {result.stderr}")
            return False

    except Exception as e:
        print(f"⚠️ 시간 동기화 중 오류: {e}")
        return False


def get_binance_server_time():
    """바이낸스 서버 시간 조회"""
    try:
        try:
            import requests
        except ImportError:
            print("⚠️ requests 모듈이 설치되지 않았습니다. 'pip install requests' 또는 'pip install -r requirements.txt'를 실행해주세요.")
            return None, None
        
        response = requests.get('https://api.binance.com/api/v3/time', timeout=5)
        if response.status_code == 200:
            server_time = response.json()['serverTime']
            server_dt = datetime.fromtimestamp(server_time / 1000, tz=timezone.utc)
            return server_time, server_dt
        return None, None
    except Exception as e:
        print(f"⚠️ 바이낸스 서버 시간 조회 오류: {e}")
        return None, None


def check_time_sync():
    """시간 동기화 상태 확인"""
    try:
        # 맥/Linux 환경에서는 시간 동기화 확인만 수행 (Windows 시간 동기화는 지원하지 않음)
        if platform.system() != 'Windows':
            local_time = datetime.now(timezone.utc)
            server_time_ms, server_time_dt = get_binance_server_time()

            if server_time_dt is None:
                print("⚠️ 바이낸스 서버 시간 조회 실패 (requests 모듈이 필요합니다)")
                print("💡 맥/Linux 환경에서는 시간 동기화 확인만 수행합니다.")
                return True  # 맥/Linux에서는 시간 동기화 확인 실패해도 계속 진행

            # 시간 차이 계산 (초 단위)
            time_diff = abs((local_time - server_time_dt).total_seconds())

            print(f"🕐 로컬 시간: {local_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"🌐 바이낸스 서버 시간: {server_time_dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"⏱️ 시간 차이: {time_diff:.2f}초")

            # 5초 이상 차이나면 경고 (하지만 계속 진행)
            if time_diff > 5:
                print(f"⚠️ 시간 차이가 큽니다! ({time_diff:.2f}초)")
                print("💡 맥/Linux 환경에서는 수동으로 시간을 확인해주세요.")
                return True  # 맥/Linux에서는 경고만 출력하고 계속 진행
            else:
                print("✅ 시간 동기화 상태 양호")
                return True

        # Windows 환경에서는 기존 로직 유지
        local_time = datetime.now(timezone.utc)
        server_time_ms, server_time_dt = get_binance_server_time()

        if server_time_dt is None:
            print("⚠️ 바이낸스 서버 시간 조회 실패")
            return False

        # 시간 차이 계산 (초 단위)
        time_diff = abs((local_time - server_time_dt).total_seconds())

        print(f"🕐 로컬 시간: {local_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🌐 바이낸스 서버 시간: {server_time_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏱️ 시간 차이: {time_diff:.2f}초")

        # 5초 이상 차이나면 경고
        if time_diff > 5:
            print(f"⚠️ 시간 차이가 큽니다! ({time_diff:.2f}초)")
            print("💡 Windows 시간 동기화를 실행합니다...")
            return False
        else:
            print("✅ 시간 동기화 상태 양호")
            return True

    except Exception as e:
        print(f"⚠️ 시간 동기화 확인 오류: {e}")
        # 맥/Linux에서는 오류가 나도 계속 진행
        if platform.system() != 'Windows':
            return True
        return False


def ensure_time_sync(max_retries=3):
    """시간 동기화 보장 (필요시 자동 동기화)"""
    try:
        print("\n" + "="*60)
        print("⏰ 시간 동기화 확인 중...")
        print("="*60)

        # 1차 확인
        if check_time_sync():
            return True

        # 동기화 필요 - Windows 시간 동기화 실행
        for attempt in range(max_retries):
            print(f"\n🔄 시도 {attempt + 1}/{max_retries}: 시간 동기화 실행")

            if sync_windows_time():
                # 동기화 후 2초 대기
                time.sleep(2)

                # 재확인
                if check_time_sync():
                    print("✅ 시간 동기화 성공!")
                    print("="*60 + "\n")
                    return True

            # 실패 시 1초 대기 후 재시도
            if attempt < max_retries - 1:
                time.sleep(1)

        # 모든 시도 실패
        print("⚠️ 시간 동기화에 실패했습니다.")
        print("💡 수동으로 Windows 시간 설정을 확인해주세요:")
        print("   1. 작업 표시줄 시계 우클릭 → '날짜/시간 조정'")
        print("   2. '시간 자동 설정' 활성화")
        print("   3. '지금 동기화' 클릭")
        print("="*60 + "\n")
        return False

    except Exception as e:
        print(f"⚠️ 시간 동기화 보장 오류: {e}")
        return False


if __name__ == "__main__":
    # 테스트 실행
    ensure_time_sync()
