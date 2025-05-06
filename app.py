import html
from fastapi import FastAPI, HTTPException, Request, Query, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from tortoise.contrib.fastapi import register_tortoise
from src.utils.chunk_utils import chunk_document
from src.utils.file_utils import load_documents_from_directory
from contextlib import asynccontextmanager
from tortoise import Tortoise
from dotenv import load_dotenv
from openai import OpenAI
import os
import faiss
import numpy as np
import json

import time
import pyaudio
import dashscope
from dashscope.api_entities.dashscope_response import SpeechSynthesisResponse
from dashscope.audio.tts_v2 import *
from dashscope import Generation
from datetime import datetime
from http import HTTPStatus
from typing import Dict
from sentence_transformers import SentenceTransformer

from src.models import ChatSession, Message

# 加载.env文件
load_dotenv()

dashscope.api_key = os.getenv("MODEL_API_KEY")
# 初始化mysql数据库配置
DATABASE_CONFIG = {
    "connections": {
        "default": {
            "engine": "tortoise.backends.mysql",
            "credentials": {
                "host": "localhost",
                "port": 3306,
                "user": "root",
                "password": "2210108lh",
                "database": "rag_history",
                "charset": "utf8mb4",
            },
        }
    },
    "apps": {
        "models": {
            "models": ["src.models", "aerich.models"],  # 修改模型路径
            "default_connection": "default",
        }
    },
}

# 全局变量
model = None
index = None
documents = []
document_to_chunks = {}
chunks_to_document = {}
all_chunks = []
client = None
# 模型
voice_model = "cosyvoice-v2"
# 音色
voice = "longxiaochun_v2"
callback = None
synthesizer = None


# 创建应用启动上下文
# 修改初始化函数为异步
# 修复生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动
    init()
    await init_mysql()
    print("应用启动完成")
    yield
    # 应用关闭
    await shutdown()


# 创建FastAPI实例时使用新的生命周期管理
app = FastAPI(lifespan=lifespan)
# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

# 添加CORS中间件允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该设置为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 初始化AI客户端、初始化模型
def init():
    global client, model

    # 初始化OpenAI客户端
    client = OpenAI(
        # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx",
        api_key=os.getenv("MODEL_API_KEY"),
        base_url=os.getenv("MODEL_BASE_URL"),
    )
    print("\nAI客户端初始化完成\n")

    # 初始化向量模型
    local_model_path = "local_m3e_model"
    if os.path.exists(local_model_path):
        model = SentenceTransformer(local_model_path)
    else:
        model = SentenceTransformer("moka-ai/m3e-base")
        model.save(local_model_path)
    print("\n模型加载完成\n")


# 定义回调接口
class Callback(ResultCallback):
    _player = None
    _stream = None

    def on_open(self):
        print("websocket is open.")
        self._player = pyaudio.PyAudio()
        self._stream = self._player.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=22050,  # 调整为标准采样率
            output=True,
            # frames_per_buffer=2048,
        )

    def on_complete(self):
        print(get_timestamp() + " speech synthesis task complete successfully.")

    def on_error(self, message: str):
        print(f"speech synthesis task failed, {message}")

    def on_close(self):
        print(get_timestamp() + " websocket is closed.")
        # 停止播放器
        self._stream.stop_stream()
        self._stream.close()
        self._player.terminate()

    def on_event(self, message):
        pass

    def on_data(self, data: bytes) -> None:
        print(get_timestamp() + " audio result length: " + str(len(data)))
        try:
            if self._stream.is_active():
                self._stream.write(data)
        except Exception as e:
            print(f"音频播放错误: {str(e)}")


# 实例化SpeechSynthesizer，并在构造方法中传入模型（model）、音色（voice）等请求参数
def init_SpeechSynthesizer():
    global callback, synthesizer
    callback = Callback()
    synthesizer = SpeechSynthesizer(
        model=voice_model,
        voice=voice,
        format=AudioFormat.PCM_22050HZ_MONO_16BIT,
        callback=callback,
    )


# 文本分块函数
def chunk_document(text, max_chars=500, overlap=20):
    """
    将中文文本按指定最大字符数分割成块，支持重叠。

    参数：
        text (str): 输入的中文文本
        max_chars (int): 每个块的最大字符数，默认为500
        overlap (int): 相邻块之间的重叠字符数，默认为5

    返回：
        list: 分割后的文本块列表
    """
    if not text:
        return []

    chunks = []
    text_length = len(text)
    start = 0

    while start < text_length:
        # 计算当前块的结束位置
        end = min(start + max_chars, text_length)
        # 确保不截断中文字符
        chunk = text[start:end]
        chunks.append(chunk)
        # 更新起始位置，考虑重叠
        start += max_chars - overlap

    return chunks


# 获取嵌入向量
def get_embeddings(texts):
    embeddings = model.encode(texts, normalize_embeddings=True)
    return np.array(embeddings)


# 修改数据库初始化函数为异步
async def init_mysql():
    try:
        await Tortoise.init(config=DATABASE_CONFIG)  # 使用Tortoise原生初始化方法
        await Tortoise.generate_schemas()  # 手动生成数据库模式
        print(f"数据库初始化成功")
    except Exception as e:
        print(f"数据库初始化失败: {str(e)}")


# 检索函数
def retrieve_docs(query, k=3):
    if index is None or not all_chunks:
        return [], []

    query_embedding = get_embeddings([query])
    distances, chunk_indices = index.search(query_embedding, k)

    # 获取包含这些chunks的原始文档
    retrieved_doc_ids = set()
    retrieved_chunks = []

    for chunk_idx in chunk_indices[0]:
        if chunk_idx >= 0 and chunk_idx < len(all_chunks):
            doc_id = chunks_to_document.get(int(chunk_idx))
            if doc_id is not None:
                retrieved_doc_ids.add(doc_id)
                retrieved_chunks.append((doc_id, all_chunks[int(chunk_idx)]))

    # 获取原始文档详情
    retrieved_docs = []
    for doc_id in retrieved_doc_ids:
        if doc_id in uploaded_documents:
            retrieved_docs.append(f"文档: {uploaded_documents[doc_id]['name']}")

    return retrieved_docs, retrieved_chunks


# 重新构建索引
def rebuild_index():
    global index, document_to_chunks, chunks_to_document, all_chunks

    # 重置数据
    document_to_chunks = {}
    chunks_to_document = {}
    all_chunks = []

    # 处理上传的文档 ，对长文档进行分块
    for doc_id, doc_data in uploaded_documents.items():
        content = doc_data.get("content", "")
        chunks = chunk_document(content)
        # 存储映射关系
        document_to_chunks[doc_id] = []
        for chunk in chunks:
            chunk_id = len(all_chunks)
            all_chunks.append(chunk)
            document_to_chunks[doc_id].append(chunk_id)
            chunks_to_document[chunk_id] = doc_id

    # 如果没有文档，不创建索引
    if not all_chunks:
        index = None
        return

    print(f"all_chunks: {all_chunks}")
    print(f"chunks_count: {len(all_chunks)}")

    # 生成嵌入
    chunk_embeddings = get_embeddings(all_chunks)

    # 初始化FAISS索引
    dimension = chunk_embeddings.shape[1]  # 768 for m3e-base
    index = faiss.IndexFlatL2(dimension)
    index.add(chunk_embeddings)

    # 保存索引
    faiss.write_index(index, "m3e_faiss_index.bin")

    # 保存映射关系
    mapping_data = {
        "doc_to_chunks": document_to_chunks,
        "chunks_to_doc": chunks_to_document,
        "all_chunks": all_chunks,
    }
    np.save("chunks_mapping.npy", mapping_data)

    print("\n索引创建并保存成功\n")


def load_documents():
    global uploaded_documents

    index_path = "docs/documents_index.json"
    if not os.path.exists(index_path):
        return

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            serialized_docs = json.load(f)

        # 加载文档元数据和内容
        for doc_id, doc_data in serialized_docs.items():
            path = doc_data.get("path")
            if path and os.path.exists(path):
                # 加载实际内容
                if path.endswith(".pdf"):
                    content_text, error = file_utils.load_pdf_file(path)
                elif path.endswith(".txt"):
                    content_text, error = file_utils.load_text_file(path)
                elif path.endswith(".docx"):
                    content_text, error = file_utils.load_docx_file(path)
                else:
                    continue

                uploaded_documents[doc_id] = {
                    "name": doc_data["name"],
                    "path": path,
                    "content": content_text,
                }

        # 重建索引
        rebuild_index()
        print("\n文档加载完成\n")
    except Exception as e:
        print(f"加载文档索引失败: {str(e)}")


# 文档和会话存储
uploaded_documents: Dict[str, Dict] = {}  # {id: {name, content, path}}
chat_sessions: Dict[str, Dict] = {}  # {id: {summary, updated_at, messages}}


# 保存和加载文档数据
def save_documents():
    # 创建一个可序列化的版本（不包含文件内容以减少文件大小）
    serializable_docs = {}
    for doc_id, doc_data in uploaded_documents.items():
        serializable_docs[doc_id] = {"name": doc_data["name"], "path": doc_data["path"]}

    with open("docs/documents_index.json", "w", encoding="utf-8") as f:
        json.dump(serializable_docs, f, ensure_ascii=False, indent=2)

# 会话历史记录 API
@app.get("/api/chat/history")
async def get_chat_history():
    try:
        # 获取所有会话数据并按创建时间倒序排列
        history = await ChatSession.all().order_by("-create_time").limit(10)
        return {
            "data": [{
                "session_id": session.id,
                "summary": session.summary,
                "create_time": session.create_time.isoformat(),
                "update_time": session.updat_time.isoformat()
            } for session in history]
        }

    except Exception as e:
        print(f"获取聊天历史失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取聊天历史失败: {str(e)}")




# 添加关闭事件
# @app.on_event("shutdown")
async def shutdown():
    await Tortoise.close_connections()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
