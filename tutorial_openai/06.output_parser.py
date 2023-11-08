import os

from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.llms import OpenAI
from langchain.output_parsers import CommaSeparatedListOutputParser
from langchain.output_parsers import (
    PydanticOutputParser,
    OutputFixingParser,
)
from langchain.output_parsers import RetryWithErrorOutputParser
from langchain.prompts import (
    PromptTemplate,
)
from pydantic import BaseModel, Field, validator

from util import config_util

config = config_util.ConfigClsf().get_config()
openai_api_key = os.getenv('OPENAI_API_KEY', config['OPENAI']['API'])

"""
일반적으로 LLM은 텍스트를 출력합니다. 하지만 보다 구조화된 정보를 얻고 싶을 수 있습니다.
이런 경우 출력 파서를 이용하여 LLM 응답을 구조화할 수 있습니다.
출력 파서는 두 가지 컨셉을 갖고 있습니다.

- Format instructions : 원하는 결과의 포멧을 지정하여 LLM에 알려줍니다.
- Parser : 원하는 텍스트 출력 구조 (보통 json) 을 추출하도록 합니다.

이 출력 구문 분석기를 사용하면 사용자가 임의의 JSON 스키마를 지정하고 해당 스키마를 준수하는 JSON 출력에 대해 LLM을 쿼리할 수 있습니다.

대규모 언어 모델은 누수가 있는 추상화라는 점에 유의하세요! 
올바른 형식의 JSON을 생성할 수 있는 충분한 용량을 갖춘 LLM을 사용해야 합니다. 
OpenAI 제품군에서 다빈치는 안정적으로 처리할 수 있지만, 퀴리는 이미 성능이 급격히 떨어집니다.

Pydantic을 사용하여 데이터 모델을 선언하세요. Pydantic의 BaseModel은 Python 데이터 클래스와 비슷하지만 실제 유형 검사 + 강제성이 있습니다.

"""


def comma_parser():
    """
    CommaSeparatedListOutputParser
    """

    output_parser = CommaSeparatedListOutputParser()
    format_instructions = output_parser.get_format_instructions()

    prompt = PromptTemplate(
        template="List five {subject}.\n{format_instructions}",
        input_variables=["subject"],
        partial_variables={"format_instructions": format_instructions}
    )

    model = OpenAI(temperature=0, openai_api_key=openai_api_key)
    _input = prompt.format(subject="ice cream flavors")
    output = model(_input)
    print(output_parser.parse(output))
    return output

"""
JSON parser

"""
class Joke(BaseModel):
    setup: str = Field(description="question to set up a joke")
    punchline: str = Field(description="answer to resolve the joke")

    # # Pydantic을 사용하면 사용자 지정 유효성 검사 로직을 쉽게 추가할 수 있습니다.
    @validator("setup")
    def question_ends_with_question_mark(cls, field):
        if field[-1] != "?":
            raise ValueError("Badly formed question!")
        return field


def user_parser():
    parser = PydanticOutputParser(pydantic_object=Joke)

    prompt = PromptTemplate(
        template="Answer the user query.\n{format_instructions}\n{query}\n",
        input_variables=["query"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )

    model = OpenAI(temperature=0,
                   callbacks=([StreamingStdOutCallbackHandler()]),
                   streaming=True ,
                   verbose=True,
                   openai_api_key=openai_api_key)

    prompt_and_model = prompt | model

    output = prompt_and_model.invoke({"query": "Tell me a joke."})
    print(output)
    return output

class Action(BaseModel):
    action: str = Field(description="action to take")
    action_input: str = Field(description="input to the action")

def retry_parser():
    parser = PydanticOutputParser(pydantic_object=Action)

    prompt = PromptTemplate(
        template="Answer the user query.\n{format_instructions}\n{query}\n",
        input_variables=["query"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )

    prompt_value = prompt.format_prompt(query="who is leo di caprios gf?")
    bad_response = '{"action": "search"}'

    """
    parser.parse(bad_response)
    
    을 실행한다면 오류 action_input이 없기 때문에 에러가 발생한다. 
    langchain.schema.output_parser.OutputParserException: Failed to parse Action from completion {"action": "search"}. Got: 1 validation error for Action
    action_input
    field required (type=value_error.missing)
    """

    model = OpenAI(temperature=0, openai_api_key=openai_api_key)

    # Auto-Fixing Parser 활용
    fix_parser = OutputFixingParser.from_llm(parser=parser, llm=model)
    print(fix_parser.parse(bad_response))

    #대신, 프롬프트 (원래 출력뿐만 아니라)를 통과하는 RetryOutputParser를 사용하여 더 나은 응답을 얻기 위해 다시 시도 할 수 있습니다.
    retry_parser = RetryWithErrorOutputParser.from_llm(parser=parser, llm=model)
    print(retry_parser.parse_with_prompt(bad_response, prompt_value))

if __name__=="__main__":
    retry_parser()