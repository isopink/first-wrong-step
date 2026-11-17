"""Controlled vocabularies shared by the diagnosis step, the problem bank and the reports.

Units follow the 2015 revised curriculum that the CSAT math section is set from.
Keeping these lists closed is what makes recommendation by skill possible: the model
must pick from them, so a tag on a student's mistake can be matched to a tag on a
past exam item.
"""

from __future__ import annotations

SUBJECTS: dict[str, dict[str, list[str]]] = {
    "수학I": {
        "지수함수와 로그함수": ["지수와 로그의 성질", "지수함수의 그래프", "로그함수의 그래프", "지수방정식과 부등식", "로그방정식과 부등식"],
        "삼각함수": ["호도법과 일반각", "삼각함수의 정의와 관계", "삼각함수의 그래프", "사인법칙", "코사인법칙"],
        "수열": ["등차수열", "등비수열", "수열의 합과 시그마", "귀납적 정의", "수학적 귀납법"],
    },
    "수학II": {
        "함수의 극한과 연속": ["함수의 극한", "극한의 계산", "함수의 연속", "사잇값 정리"],
        "미분": ["미분계수와 도함수", "접선의 방정식", "평균값 정리", "증가와 감소", "극대와 극소", "그래프 개형", "방정식과 부등식에의 활용", "속도와 가속도"],
        "적분": ["부정적분", "정적분의 계산", "정적분으로 정의된 함수", "넓이", "속도와 거리"],
    },
    "미적분": {
        "수열의 극한": ["수열의 극한", "급수", "등비급수"],
        "미분법": ["지수 로그함수의 미분", "삼각함수의 미분", "여러 가지 미분법", "도함수의 활용"],
        "적분법": ["치환적분", "부분적분", "정적분의 활용"],
    },
    "확률과 통계": {
        "경우의 수": ["순열과 조합", "중복순열과 중복조합", "이항정리"],
        "확률": ["확률의 뜻과 덧셈정리", "조건부확률", "독립과 종속", "독립시행"],
        "통계": ["확률분포", "이항분포", "정규분포", "통계적 추정"],
    },
    "기하": {
        "이차곡선": ["포물선", "타원", "쌍곡선", "이차곡선의 접선"],
        "평면벡터": ["벡터의 연산", "벡터의 내적", "평면 운동"],
        "공간도형과 공간좌표": ["직선과 평면의 위치관계", "삼수선 정리", "정사영", "공간좌표"],
    },
}

ERROR_TYPES: dict[str, str] = {
    "concept": "개념 오해: 정의, 정리, 공식을 잘못 알고 있다",
    "condition": "조건 누락: 문제에 주어진 조건이나 범위를 쓰지 않았다",
    "case": "경우 누락: 나눠야 할 경우를 빠뜨렸다",
    "algebra": "식 변형 오류: 이항, 전개, 인수분해, 부호에서 틀렸다",
    "arithmetic": "계산 실수: 사칙연산 값이 틀렸다",
    "logic": "논리 비약: 근거 없이 다음 줄로 넘어갔다",
    "misread": "문제 오독: 묻는 것을 잘못 읽었다",
    "incomplete": "미완성: 풀이가 중간에 멈췄다",
}


def all_skills() -> list[str]:
    return [s for units in SUBJECTS.values() for skills in units.values() for s in skills]


def unit_of(skill: str) -> tuple[str, str] | None:
    for subject, units in SUBJECTS.items():
        for unit, skills in units.items():
            if skill in skills:
                return subject, unit
    return None


def vocab_prompt() -> str:
    """The closed lists as plain text, for system prompts."""
    lines = ["Skill tags (use these strings exactly):"]
    for subject, units in SUBJECTS.items():
        for unit, skills in units.items():
            lines.append(f"- {subject} / {unit}: " + ", ".join(skills))
    lines.append("")
    lines.append("Error types (use the key on the left):")
    for key, desc in ERROR_TYPES.items():
        lines.append(f"- {key}: {desc}")
    return "\n".join(lines)
