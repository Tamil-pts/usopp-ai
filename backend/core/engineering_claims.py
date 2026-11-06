"""Typed publication records. Schema validity never substitutes for source proof."""
from typing import Any,Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator


class StaticEngineeringFact(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    id:str=Field(pattern=r'^F[1-9][0-9]*$')
    kind:Literal['physical_mapping','rung_condition','assignment']
    relationshipId:str=Field(min_length=1)
    text:str=Field(min_length=1)
    sourceIds:list[str]=Field(min_length=1)
    details:dict[str,Any]
    status:Literal['source-verified-static']

    @field_validator('sourceIds')
    @classmethod
    def sources(cls,value):
        import re
        if len(value)!=len(set(value)) or any(not re.fullmatch(r'S[1-9][0-9]*',item) for item in value):
            raise ValueError('Source IDs must be unique, explicit evidence identities.')
        return value
