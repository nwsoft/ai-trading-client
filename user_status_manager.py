#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
사용자 상태 관리 모듈
- 중복 실행 방지
- 원격 상태 체크
- 프로세스 및 파일 정리
"""

import os
import sys
import time
import threading
import requests
import psutil
import shutil
import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class UserStatusManager:
    """사용자 상태 관리 클래스"""
    
    def __init__(self, backend_api=None, settings=None, policy_update_callback=None):
        self.backend_api = backend_api
        self.settings = settings or {}
        self.policy_update_callback = policy_update_callback
        self.status_thread = None
        self.is_running = False
        self.check_interval = 60
        self.initial_delay = 5
        
        # 🔧 환경 설정 (PyInstaller 배포 환경 대응)
        if getattr(sys, 'frozen', False):
            # 배포 환경 - path_utils 사용
            try:
                from path_utils import get_token_file_path
                self.env_file = get_token_file_path()
            except ImportError:
                # path_utils 사용 실패 시 기본 경로 사용
                from path_utils import get_app_data_dir
                data_dir = get_app_data_dir()
                self.env_file = os.path.join(data_dir, 'token.json')
        else:
            # 개발 환경 - path_utils 사용
            try:
                from path_utils import get_token_file_path
                self.env_file = get_token_file_path()
            except ImportError:
                # path_utils 사용 실패 시 기본 경로 사용
                self.env_file = os.path.join(os.path.dirname(__file__), 'data', 'token.json')
            
        self.server_url = "https://daltrading.net"  # 백엔드 서버 URL
        
        logger.info("UserStatusManager 초기화 완료")
        logger.info(f"🔍 토큰 파일 경로 설정: {self.env_file}")
        logger.info(f"🔧 실행 환경: {'배포 (PyInstaller)' if getattr(sys, 'frozen', False) else '개발'}")
        logger.info(f"🌐 백엔드 서버: {self.server_url}")
        
        # 서버 연결 테스트
        self._test_server_connection()
    
    def start_status_checker(self) -> Optional[threading.Thread]:
        """상태 체크 스레드 시작"""
        if self.is_running:
            logger.warning("상태 체크가 이미 실행 중입니다.")
            return self.status_thread
            
        logger.info("상태 체크 스레드 시작...")
        self.is_running = True
        
        def status_check_loop():
            """상태 체크 루프"""
            logger.info("상태 체크 스레드가 시작되었습니다.")
            
            # 첫 체크는 지정된 시간 후에 시작
            logger.info(f"첫 상태 체크는 {self.initial_delay}초 후에 시작됩니다...")
            time.sleep(self.initial_delay)
            
            while self.is_running:
                try:
                    logger.info("사용자 상태 체크 시작...")
                    check_result = self.check_user_status()
                    
                    if not check_result:
                        logger.warning("상태 체크 실패. 프로그램을 종료합니다.")
                        self.cleanup_and_exit()
                        break
                        
                    logger.info("상태 체크 완료. 정상 작동 중...")
                    logger.info(f"다음 체크까지 {self.check_interval}초 대기 중...")
                    
                    # 종료 신호 체크하면서 대기
                    for _ in range(self.check_interval):
                        if not self.is_running:
                            break
                        time.sleep(1)
                        
                except Exception as e:
                    logger.error(f"상태 체크 중 오류 발생: {e}")
                    self.cleanup_and_exit()
                    break
            
            logger.info("상태 체크 스레드가 종료되었습니다.")
        
        self.status_thread = threading.Thread(target=status_check_loop, daemon=True)
        self.status_thread.start()
        logger.info("상태 체크 스레드가 백그라운드에서 실행 중입니다.")
        
        return self.status_thread
    
    def stop_status_checker(self):
        """상태 체크 스레드 중지"""
        logger.info("상태 체크 스레드 중지 요청...")
        self.is_running = False
        
        if self.status_thread and self.status_thread.is_alive():
            logger.info("상태 체크 스레드 종료 대기 중...")
            self.status_thread.join(timeout=5)
            
        logger.info("상태 체크 스레드가 중지되었습니다.")
    
    def _test_server_connection(self):
        """백엔드 서버 연결 테스트"""
        try:
            logger.info("🌐 백엔드 서버 연결 테스트 중...")
            
            # 실제 존재하는 엔드포인트로 연결 테스트 (로그인 페이지 사용)
            response = requests.get(
                f"{self.server_url}/auth/api_login",
                timeout=5
            )
            
            # 404가 아닌 응답이면 서버가 살아있음 (405 Method Not Allowed도 정상)
            if response.status_code not in [404]:
                logger.info("✅ 백엔드 서버 연결 성공")
                return True
            else:
                logger.warning(f"⚠️ 백엔드 서버 응답 이상: {response.status_code}")
                return False
                
        except requests.exceptions.ConnectTimeout:
            logger.warning("⚠️ 백엔드 서버 연결 시간 초과")
            return False
        except requests.exceptions.ConnectionError:
            logger.warning("⚠️ 백엔드 서버 연결 실패 (서버 다운 또는 네트워크 문제)")
            return False
        except Exception as e:
            logger.warning(f"⚠️ 백엔드 서버 연결 테스트 실패: {e}")
            return False
    
    def check_user_status(self) -> bool:
        """서버에서 사용자 상태 체크"""
        try:
            logger.info("사용자 상태 체크 시작...")
            logger.info(f"🔍 토큰 파일 경로: {self.env_file}")
            
            # 토큰 파일에서 사용자 정보 읽기
            if not os.path.exists(self.env_file):
                logger.error(f"❌ 토큰 파일을 찾을 수 없습니다: {self.env_file}")
                return False
            
            logger.info(f"✅ 토큰 파일 발견: {self.env_file}")
            
            import json
            with open(self.env_file, 'r', encoding='utf-8') as f:
                token_data = json.load(f)
            
            # 토큰 파일 구조에 맞게 수정
            user_info = token_data.get('user_info', {})
            user_id = user_info.get('id')
            session_id = user_info.get('session_id')
            access_token = str(token_data.get('access_token') or '').strip()
            
            if not user_id or not session_id:
                logger.error("사용자 정보가 불완전합니다.")
                return False
            
            logger.info(f"사용자 정보 확인: ID={user_id}, SESSION_ID={session_id[:8]}...")
            
            # 서버에 상태 체크 요청
            logger.info("서버에 상태 체크 요청 중...")
            response = requests.post(
                f"{self.server_url}/auth/check_status",
                json={"id": user_id, "session_id": session_id},
                headers={"Authorization": f"Bearer {access_token}"} if access_token else None,
                timeout=10
            )
            
            logger.info(f"서버 응답: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"서버 응답 데이터: {data}")
                
                if not data.get("is_active", False) or data.get("force_quit", False):
                    logger.warning("사용자 계정이 비활성화되었거나 다른 곳에서 로그인되었습니다.")
                    logger.warning(f"메시지: {data.get('message', '프로그램을 종료합니다.')}")
                    return False

                server_grade = str(data.get("user_grade") or user_info.get("user_grade") or "").strip()
                server_policy = data.get("membership_policy")
                if server_grade and isinstance(server_policy, dict):
                    refreshed_access_token = str(data.get("access_token") or "").strip()
                    if refreshed_access_token:
                        token_data["access_token"] = refreshed_access_token
                    user_info["user_grade"] = server_grade
                    user_info["membership_policy"] = server_policy
                    token_data["user_info"] = user_info
                    temp_path = f"{self.env_file}.tmp"
                    with open(temp_path, "w", encoding="utf-8") as token_file:
                        json.dump(token_data, token_file, ensure_ascii=False, indent=2)
                    os.replace(temp_path, self.env_file)
                    if callable(self.policy_update_callback):
                        self.policy_update_callback(server_grade, server_policy)
                return True
            else:
                logger.error(f"서버 응답 오류: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"상태 체크 중 오류 발생: {e}")
            return False
    
    def cleanup_processes(self):
        """실행 중인 관련 프로세스 정리"""
        try:
            logger.info("프로세스 정리 시작...")
            
            # 현재 실행 중인 프로세스 목록 가져오기
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'exe']):
                try:
                    cmdline = proc.info['cmdline']
                    if not cmdline:
                        continue
                    
                    # 프로세스의 전체 경로 확인
                    process_path = ' '.join(cmdline).lower()
                    
                    # 관련 프로세스 종료 (현재 프로세스 제외)
                    current_pid = os.getpid()
                    if proc.info['pid'] == current_pid:
                        continue
                    
                    # Noah AI Client 관련 프로세스 종료
                    if ('python' in proc.info['name'].lower() and 
                        ('main.py' in process_path or 'aiautotrade' in process_path)):
                        logger.info(f"Noah AI Client 프로세스 종료 중: {proc.info['pid']}")
                        proc.kill()
                    
                    # 기타 관련 프로세스들
                    elif ('python' in proc.info['name'].lower() and 
                          ('autotrade.py' in process_path or 'trading' in process_path)):
                        logger.info(f"Trading 프로세스 종료 중: {proc.info['pid']}")
                        proc.kill()
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            # 프로세스가 완전히 종료될 때까지 잠시 대기
            time.sleep(2)
            
            logger.info("프로세스 정리 완료")
            
        except Exception as e:
            logger.error(f"프로세스 정리 중 오류 발생: {e}")
    
    def cleanup_files(self):
        """임시 파일 정리"""
        try:
            logger.info("파일 정리 시작...")
            
            # 임시 로그 파일 정리 (선택적)
            temp_dirs = [
                os.path.join(os.path.expanduser("~"), ".ai_trading", "logs"),
                os.path.join(os.path.expanduser("~"), ".streamlit", "session")
            ]
            
            for temp_dir in temp_dirs:
                if os.path.exists(temp_dir):
                    try:
                        if os.path.isfile(temp_dir):
                            logger.info(f"임시 파일 삭제: {temp_dir}")
                            os.remove(temp_dir)
                        else:
                            logger.info(f"임시 디렉토리 삭제: {temp_dir}")
                            shutil.rmtree(temp_dir)
                    except Exception as e:
                        logger.warning(f"파일 삭제 실패 {temp_dir}: {e}")
            
            logger.info("파일 정리 완료")
            
        except Exception as e:
            logger.error(f"파일 정리 중 오류 발생: {e}")
    
    def cleanup_and_exit(self):
        """정리 작업 후 프로그램 종료"""
        try:
            logger.warning("프로그램 종료 프로세스 시작...")
            
            # 상태 체크 중지
            self.is_running = False
            
            # 프로세스 정리
            self.cleanup_processes()
            
            # 파일 정리
            self.cleanup_files()
            
            logger.warning("정리 작업 완료. 프로그램을 종료합니다.")
            
            # CustomTkinter 애플리케이션 종료 (PyQt5 의존성 제거)
            try:
                # CustomTkinter는 별도 종료 처리 불필요
                pass
            except Exception as e:
                logger.error(f"애플리케이션 종료 중 오류: {e}")
            
            # 강제 종료
            os._exit(0)
            
        except Exception as e:
            logger.error(f"정리 작업 중 오류 발생: {e}")
            os._exit(1)


# 전역 상태 관리자 인스턴스
_status_manager = None

def get_status_manager(backend_api=None, settings=None, policy_update_callback=None) -> UserStatusManager:
    """상태 관리자 싱글톤 인스턴스 반환"""
    global _status_manager
    if _status_manager is None:
        _status_manager = UserStatusManager(backend_api, settings, policy_update_callback)
    elif policy_update_callback is not None:
        _status_manager.policy_update_callback = policy_update_callback
    return _status_manager

def start_user_status_monitoring(backend_api=None, settings=None) -> UserStatusManager:
    """사용자 상태 모니터링 시작 (편의 함수)"""
    manager = get_status_manager(backend_api, settings)
    manager.start_status_checker()
    return manager

def stop_user_status_monitoring():
    """사용자 상태 모니터링 중지 (편의 함수)"""
    global _status_manager
    if _status_manager:
        _status_manager.stop_status_checker()


if __name__ == "__main__":
    # 테스트용 코드
    logging.basicConfig(level=logging.INFO)
    manager = UserStatusManager()
    manager.start_status_checker()
    
    try:
        # 테스트를 위해 잠시 실행
        time.sleep(10)
    except KeyboardInterrupt:
        print("테스트 중단")
    finally:
        manager.stop_status_checker()
