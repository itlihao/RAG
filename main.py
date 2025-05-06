import os
from openai import OpenAI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from fastapi import FastAPI, Request, Query
from fastapi.responses import StreamingResponse
import json

app = FastAPI()
# 允许跨域请求，适配前端
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(
    # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx",
    api_key="sk-a33c39c67d1a4b3a8a306b0594b31815",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)


async def generate_answer(prompt: str):
    try:
        response = client.chat.completions.create(
            # 模型列表：https://help.aliyun.com/zh/model-studio/getting-started/models
            model="qwen3-32b",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "你是谁？"},
            ],
            stream=True,  # 开启流式输出
            stream_options={"include_usage": True}
            # Qwen3模型通过enable_thinking参数控制思考过程（开源版默认True，商业版默认False）
            # 使用Qwen3开源版模型时，若未启用流式输出，请将下行取消注释，否则会报错
            # extra_body={"enable_thinking": False},
        )
        full_content = ""
        usage_data = {}

    # for chunk in response:
    #     # print(chunk.model_dump_json())
    #     # 添加空值检查
    #     if chunk.choices and len(chunk.choices) > 0:
    #         delta = chunk.choices[0].delta
    #         if delta and delta.content:
    #             full_content += delta.content
    #     if chunk.usage:
    #         usage_data = chunk.usage.model_dump()
        for chunk in response:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                yield f"data: {json.dumps({'content': content})}\n\n"
                await asyncio.sleep(0.01)  # 添加小延迟确保流式输出

            if chunk.choices[0].finish_reason is not None:
                yield "data: [DONE]\n\n"
                break

    except Exception as e:
        print(f"Error generating stream: {e}")
        yield f"data: {json.dumps({'content': f'错误: {str(e)}'})}\n\n"
        yield "data: [DONE]\n\n"
    # return {
    #     "content": full_content.strip(),
    #     "usage": usage_data,
    #     "model": "qwen3-32b"
    # }


# @app.post("/stream")
# async def stream_post(request: Request):
#     body = await request.json()
#     prompt = body.get("prompt", "你好，请简单介绍一下自己！")
#     return StreamingResponse(
#         generate_stream(prompt),
#         media_type="text/event-stream",
#         headers={
#             "Cache-Control": "no-cache",
#             "Connection": "keep-alive",
#             "Transfer-Encoding": "chunked"
#         }
#     )

@app.get("/stream")
async def stream_get(prompt: str = Query("你好，请简单介绍一下自己！")):
    return StreamingResponse(
        generate_answer(prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked"
        }
    )

# 运行服务
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
