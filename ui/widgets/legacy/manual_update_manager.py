"""
메뉴얼 업데이트 관리자 - 사용메뉴얼 콘텐츠 동적 로드 및 업데이트
"""

import json
import os
from datetime import datetime
from path_utils import get_app_base_dir

class ManualUpdateManager:
    """메뉴얼 업데이트 관리자"""

    def __init__(self):
        base_docs = os.path.join(get_app_base_dir(), "docs")
        # 우선순위: USER_GUIDE.md > MASTER_DOCUMENTATION.md > USER_MANUAL_CONTENT.md(레거시)
        candidates = [
            os.path.join(base_docs, "USER_GUIDE.md"),
            os.path.join(base_docs, "MASTER_DOCUMENTATION.md"),
            os.path.join(base_docs, "USER_MANUAL_CONTENT.md"),
        ]
        self.manual_content_path = next((p for p in candidates if os.path.exists(p)), candidates[0])
        self.version_info_path = os.path.join(base_docs, "manual_version.json")
        self.cached_content = None
        self.last_update_check = None
        
    def get_manual_content(self):
        """메뉴얼 콘텐츠 로드"""
        try:
            # 파일이 존재하는지 확인
            if not os.path.exists(self.manual_content_path):
                return self.get_default_content()
            
            # 파일 수정 시간 확인
            file_mtime = os.path.getmtime(self.manual_content_path)
            
            # 캐시된 내용이 있고 파일이 변경되지 않았다면 캐시 사용
            if (self.cached_content and 
                self.last_update_check and 
                file_mtime <= self.last_update_check):
                return self.cached_content
            
            # 파일 읽기
            with open(self.manual_content_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 캐시 업데이트
            self.cached_content = content
            self.last_update_check = file_mtime
            
            return content
            
        except Exception as e:
            print(f"메뉴얼 콘텐츠 로드 실패: {e}")
            return self.get_default_content()
    
    def get_version_info(self):
        """버전 정보 로드"""
        try:
            if os.path.exists(self.version_info_path):
                with open(self.version_info_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return self.get_default_version_info()
        except Exception as e:
            print(f"버전 정보 로드 실패: {e}")
            return self.get_default_version_info()

    def get_content_path(self) -> str:
        """현재 사용 중인 메뉴얼 파일 경로 반환"""
        return self.manual_content_path
    
    def check_for_updates(self):
        """업데이트 확인"""
        try:
            version_info = self.get_version_info()
            current_version = version_info.get('current_version', '1.0.0')
            last_check = version_info.get('last_check', '')
            
            # 마지막 확인 시간이 24시간 이내라면 스킵
            if last_check:
                last_check_time = datetime.fromisoformat(last_check)
                if (datetime.now() - last_check_time).total_seconds() < 86400:  # 24시간
                    return False
            
            # 업데이트 확인 로직 (실제로는 서버나 파일 기반으로 확인)
            # 여기서는 간단히 파일 수정 시간으로 확인
            if os.path.exists(self.manual_content_path):
                file_mtime = os.path.getmtime(self.manual_content_path)
                last_update = version_info.get('last_update', '')
                
                if last_update:
                    last_update_time = datetime.fromisoformat(last_update)
                    if file_mtime > last_update_time.timestamp():
                        return True
            
            return False
            
        except Exception as e:
            print(f"업데이트 확인 실패: {e}")
            return False
    
    def update_version_info(self):
        """버전 정보 업데이트"""
        try:
            version_info = {
                'current_version': '1.0.0',
                'last_check': datetime.now().isoformat(),
                'last_update': datetime.now().isoformat(),
                'update_available': False
            }
            
            with open(self.version_info_path, 'w', encoding='utf-8') as f:
                json.dump(version_info, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"버전 정보 업데이트 실패: {e}")
    
    def get_default_content(self):
        """기본 메뉴얼 콘텐츠 반환"""
        return """# NoahAI 사용메뉴얼

## 개요
NoahAI는 AI 금융 의사결정 인프라 및 금융 동반자 플랫폼입니다.

## 주요 기능
- AI 기반 자동 거래
- 실시간 시장 분석
- 멀티 거래소 지원
- 자연어 대화 인터페이스

## 사용법
1. 거래소 API 설정
2. 기본 설정 구성
3. AI 학습 시작
4. 자동 거래 시작

## 문제해결
자주 묻는 질문과 해결 방법을 확인하세요.

더 자세한 내용은 메뉴얼 파일을 확인해주세요."""
    
    def get_default_version_info(self):
        """기본 버전 정보 반환"""
        return {
            'current_version': '1.0.0',
            'last_check': datetime.now().isoformat(),
            'last_update': datetime.now().isoformat(),
            'update_available': False
        }
    
    def get_manual_sections(self):
        """메뉴얼 섹션별로 분리하여 반환"""
        content = self.get_manual_content()

        sections = {
            'overview': '',
            'features': '',
            'usage': '',
            'dashboard': '',
            'advantages': '',
            'ai_services': '',
            'troubleshooting': ''
        }

        try:
            lines = content.split('\n')

            # 개요: 첫 번째 헤더 전까지 텍스트
            overview_lines = []
            i = 0
            while i < len(lines) and not lines[i].lstrip().startswith('##'):
                overview_lines.append(lines[i])
                i += 1
            sections['overview'] = '\n'.join(overview_lines).strip()

            # 헤더별로 섹션 나누기
            current_title = None
            current_buffer = []
            parsed_sections = []  # list of (title, text)

            for line in lines:
                if line.lstrip().startswith('##'):
                    if current_title is not None:
                        parsed_sections.append((current_title, '\n'.join(current_buffer).strip()))
                    current_title = line.lstrip('#').strip()
                    current_buffer = []
                else:
                    current_buffer.append(line)
            if current_title is not None:
                parsed_sections.append((current_title, '\n'.join(current_buffer).strip()))

            # 키워드 매핑으로 채우기
            def find_by_keywords(keywords):
                for title, text in parsed_sections:
                    title_norm = title.replace(' ', '')
                    if any(k in title or k in title_norm for k in keywords):
                        return f"## {title}\n\n{text}".strip()
                return ''

            sections['features'] = find_by_keywords(['주요 기능', '완전 자동화', '기능']) or sections['features']
            sections['usage'] = find_by_keywords(['시작하기', '사용법']) or sections['usage']
            # 대시보드 전용 섹션(최근 문서의 "대시보드 사용법"을 우선 사용)
            sections['dashboard'] = find_by_keywords(['대시보드 사용법', '대시보드', '시장 트렌드', '거래 통계']) or sections['dashboard']
            sections['advantages'] = find_by_keywords(['장점', '튜닝 팁', '고급 기능']) or sections['advantages']
            sections['ai_services'] = find_by_keywords(['AI 서비스', 'AI', '어시스턴트']) or sections['ai_services']
            sections['troubleshooting'] = find_by_keywords(['문제해결', 'Troubleshooting', '보안', '안전']) or sections['troubleshooting']

            # 비어있는 섹션은 개요/사용법 일부로 폴백
            if not sections['features']:
                sections['features'] = sections['overview']
            if not sections['usage']:
                sections['usage'] = sections['overview']

        except Exception as e:
            print(f"메뉴얼 섹션 분리 실패: {e}")
            for section in sections:
                sections[section] = "내용을 로드할 수 없습니다."

        return sections
