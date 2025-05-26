# message_formatter.py
"""
Slack에 보낼 메시지 포맷팅 처리 모듈
"""
import re
import logging
from typing import List

from config import Config

logger = logging.getLogger()

class MessageFormatter:
    """Slack 메시지 포맷팅 및 분할 처리"""

    @staticmethod
    def split_message(message: str, max_len: int = Config.MAX_LEN_SLACK) -> List[str]:
        """메시지를 max_len 이내 청크로 분할"""
        # 메시지가 비어 있거나 max_len보다 작으면 그대로 반환
        if not message or len(message) <= max_len:
            return [message]

        # 코드 블록으로 분할
        parts = []
        segments = message.split("```")

        for i, segment in enumerate(segments):
            if not segment:  # 빈 세그먼트 건너뛰기
                continue

            if i % 2 == 1:  # 코드 블록인 경우
                # 코드 블록 포맷 유지
                code_parts = MessageFormatter._split_text(f"```{segment}```", max_len)
                parts.extend(code_parts)
            else:
                # 일반 텍스트 - 단락별로 분할
                text_parts = MessageFormatter._split_text(segment, max_len)
                parts.extend(text_parts)

        # 최종 정리 - 모든 부분이 max_len을 초과하지 않도록
        result = []
        current = ""

        for part in parts:
            if len(current) + len(part) + 2 <= max_len:
                if current:
                    current += "\n\n" + part
                else:
                    current = part
            else:
                if current:
                    result.append(current)
                current = part

        if current:
            result.append(current)

        return result

    @staticmethod
    def _split_text(text: str, max_len: int) -> List[str]:
        """단락별로 텍스트 분할 (헬퍼 메소드)"""
        if len(text) <= max_len:
            return [text]

        parts = text.split("\n\n")
        result = []
        current = ""

        for part in parts:
            # 단일 부분이 max_len보다 길면 문장별로 분할
            if len(part) > max_len:
                sentences = re.split(r'(?<=[.!?])\s+', part)
                for sentence in sentences:
                    if len(current) + len(sentence) + 2 <= max_len:
                        if current:
                            current += " " + sentence
                        else:
                            current = sentence
                    else:
                        if current:
                            result.append(current)
                        current = sentence
            elif len(current) + len(part) + 2 <= max_len:
                if current:
                    current += "\n\n" + part
                else:
                    current = part
            else:
                if current:
                    result.append(current)
                current = part

        if current:
            result.append(current)

        return result