#!/usr/bin/env python3
"""
대시보드에서 제거된 테마 관련 메서드 호출들을 삭제하는 스크립트
"""
import re
from pathlib import Path

def remove_theme_method_calls(file_path: str) -> int:
    """
    _register_themable, _register_button_theme, _register_text_widget 호출 제거
    
    Returns:
        제거된 라인 수
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 백업 생성
    backup_path = file_path + '.backup_theme_calls'
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    # 제거할 패턴들
    patterns = [
        r'^\s*self\._register_themable\([^)]+\)\s*$',
        r'^\s*self\._register_button_theme\([^)]+\)\s*$',
        r'^\s*self\._register_text_widget\([^)]+\)\s*$',
    ]
    
    removed_count = 0
    new_lines = []
    
    for line in lines:
        should_remove = False
        for pattern in patterns:
            if re.match(pattern, line):
                should_remove = True
                removed_count += 1
                print(f"제거: {line.strip()}")
                break
        
        if not should_remove:
            new_lines.append(line)
    
    # 파일 저장
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    return removed_count

if __name__ == "__main__":
    dashboard_path = r"c:\Users\super\SynologyDrive\Works\크몽용바이낸스신버전\noahai_client\ui\dashboard_modern.py"
    
    print(f"대시보드 파일 처리 중: {dashboard_path}")
    count = remove_theme_method_calls(dashboard_path)
    print(f"\n✅ 총 {count}개 라인 제거 완료")
    print(f"백업 파일: {dashboard_path}.backup_theme_calls")
