"""
Lambda 함수 진입점 모듈
AWS Lambda 함수 핸들러를 정의합니다.
"""
from slackbot_core import lambda_handler

def handler(event, context):
    """
    Lambda 함수 핸들러 - Slack 이벤트 처리
    
    Args:
        event (dict): Lambda 이벤트 데이터
        context: Lambda 컨텍스트 객체
        
    Returns:
        dict: HTTP 응답
    """
    return lambda_handler(event, context)