import faiss
from sentence_transformers import SentenceTransformer
import numpy as np
import os
from openai import OpenAI
from utils.file_utils import load_documents_from_directory
from fastapi import FastAPI
import uvicorn
#导入utils里面的chunk-utils
from utils.chunk_utils import chunk_document


os.environ["TOKENIZERS_PARALLELISM"] = "false"

client = OpenAI(
    # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx",
    api_key="sk-a33c39c67d1a4b3a8a306b0594b31815",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)


def generate_answer(query, retrieved_docs, retrieved_chunks):
    """
    基于检索到的文档生成回答

    参数:
        query: 用户查询
        retrieved_docs: 检索到的完整文档
        retrieved_chunks: 检索到的文档块

    返回:
        生成的回答
    """
    # 构建上下文，包含原始文档和相关块
    context = "原始文档:\n" + "\n".join(retrieved_docs)

    # 添加相关块信息
    context += "\n\n相关文本块:\n"
    for doc_id, chunk in retrieved_chunks:
        context += f"[文档{doc_id}] {chunk}\n"

    prompt = f"上下文信息:\n{context}\n\n问题: {query}\n请基于上下文信息回答问题:"

    response = client.chat.completions.create(
        # 模型列表：https://help.aliyun.com/zh/model-studio/getting-started/models
        model="qwen3-32b",
        messages=[
            {"role": "system", "content": "You are a helpful assistant. 严格回答问题，不知道就回答不知道"},
            {"role": "user", "content": prompt},
        ],
        stream=True,  # 开启流式输出
        stream_options={"include_usage": True}
        # Qwen3模型通过enable_thinking参数控制思考过程（开源版默认True，商业版默认False）
        # 使用Qwen3开源版模型时，若未启用流式输出，请将下行取消注释，否则会报错
        # extra_body={"enable_thinking": False},
    )
    full_content = ""
    usage_data = {}

    for chunk in response:
        # print(chunk.model_dump_json())
        # 添加空值检查
        if chunk.choices and len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                full_content += delta.content
        if chunk.usage:
            usage_data = chunk.usage.model_dump()

    return {
        "content": full_content.strip(),
        "usage": usage_data,
        "model": "qwen3-32b"
    }


# 数据
# documents = [
#     "界面新闻是中国具有影响力的原创财经新媒体，由上海报业集团出品，2014年9月创立。界面新闻客户端曾被中央网信办评为 App影响力十佳。2017—2022年位居艾瑞商业资讯类移动App指数第一名",
#     "企业价值观：真实准确、客观公正、有担当 ，Slogan：界面新闻，只服务于独立思考的人群",
#     "创始人： 何力，毕业于首都师范大学，2014年参与创立界面新闻并担任CEO，界面新闻是中国具有影响力的原创财经新媒体，由上海报业集团出品"
# ]
documents, sources, errors = load_documents_from_directory("./docs")

# 显示结果
print(f"\n成功加载 {len(documents)} 个文档:")
for i, (doc, source) in enumerate(zip(documents, sources)):
    print(f"\n文档 {i+1} 来源: {source}")
    # 只显示文档的开头部分
    preview = doc[:200] + "..." if len(doc) > 200 else doc
    print(f"内容预览: {preview}")

# 如果有错误，显示错误信息
if errors:
    print("\n加载过程中出现以下错误:")
    for error in errors:
        print(f"- {error}")


# 加载 M3E 模型（先检查本地是否存在）
local_model_path = './local_m3e_model'
if os.path.exists(local_model_path):
    print(f"从本地加载模型: {local_model_path}")
    model = SentenceTransformer(local_model_path)
else:
    print(f"本地模型不存在，从网络加载: moka-ai/m3e-base")
    model = SentenceTransformer('moka-ai/m3e-base')
    # 保存到本地，以便下次使用
    print(f"保存模型到本地: {local_model_path}")
    model.save(local_model_path)
# 打印加载成功
print("模型加载成功！\n")


def get_embeddings(texts):
    embeddings = model.encode(texts, normalize_embeddings=True)
    return np.array(embeddings)


# 文档和chunk的映射关系
document_to_chunks = {}
chunks_to_document = {}
all_chunks = []

# 索引文件路径
index_file_path = "./m3e_faiss_index.bin"
chunks_map_path = "./chunks_mapping.npy"


def create_faiss_index(documents):
    global document_to_chunks, chunks_to_document, all_chunks
    # 添加索引
    # index_file_path = "m3e_faiss_index.bin"
    # 判断是否已存在索引文件
    if os.path.exists(index_file_path) and os.path.exists(chunks_map_path):
        print(f"从本地加载索引和映射: {index_file_path}, {chunks_map_path}")
        index = faiss.read_index(index_file_path)
        # 加载映射关系
        mapping_data = np.load(chunks_map_path, allow_pickle=True).item()
        document_to_chunks = mapping_data['doc_to_chunks']
        chunks_to_document = mapping_data['chunks_to_doc']
        all_chunks = mapping_data['all_chunks']
    else:
        print("本地索引不存在，创建新索引")
        # 处理文档并分块
        for doc_id, doc in enumerate(documents):
            # 对长文档进行分块
            chunks = chunk_document(doc)

            # 存储映射关系
        document_to_chunks[doc_id] = []
        for chunk in chunks:
            chunk_id = len(all_chunks)
            all_chunks.append(chunk)
            document_to_chunks[doc_id].append(chunk_id)
            chunks_to_document[chunk_id] = doc_id

        # 生成文档块嵌入
        chunk_embeddings = get_embeddings(all_chunks)

        # 初始化 FAISS 索引
        dimension = chunk_embeddings.shape[1]  # 768 for m3e-base
        index = faiss.IndexFlatL2(dimension)
        index.add(chunk_embeddings)

        # 保存索引
        faiss.write_index(index, index_file_path)

        # 保存映射关系
        mapping_data = {
            'doc_to_chunks': document_to_chunks,
            'chunks_to_doc': chunks_to_document,
            'all_chunks': all_chunks
        }
        np.save(chunks_map_path, mapping_data)

        print(f"索引创建并保存成功: {index_file_path}\n")
    return index


# 从索引中获取相关文档内容
def retrieve_docs(query, index, k=2):
    """
    检索最相关的文档

    参数:
        query: 查询文本
        index: FAISS索引
        k: 返回的相关chunk数量

    返回:
        按相关性排序的原始文档列表
    """
    query_embedding = get_embeddings([query])
    distances, chunk_indices = index.search(query_embedding, k)

    # 获取包含这些chunks的原始文档ID
    retrieved_doc_ids = set()
    retrieved_chunks = []

    for chunk_idx in chunk_indices[0]:
        if chunk_idx >= 0 and chunk_idx < len(all_chunks):  # 确保索引有效
            doc_id = chunks_to_document.get(int(chunk_idx))
            if doc_id is not None:
                retrieved_doc_ids.add(doc_id)
                retrieved_chunks.append((doc_id, all_chunks[int(chunk_idx)]))

    # 获取原始文档
    retrieved_docs = [documents[doc_id] for doc_id in retrieved_doc_ids]

    # 返回文档和对应的相关块
    return retrieved_docs, retrieved_chunks


# def main():
#     index = create_faiss_index(documents)

#     query = "缺勤怎么处理"
#     retrieved_docs, retrieved_chunks = retrieve_docs(query, index)

#     # 打印检索到的文档
#     # print("检索到的文档：")
#     # for doc in retrieved_docs:
#     #     print(doc)

#     # 打印检索到的文本块
#     print("\n检索到的相关文本块：")
#     for doc_id, chunk in retrieved_chunks:
#         print(f"[文档{doc_id}] {chunk}")

#     answer = generate_answer(query, retrieved_docs, retrieved_chunks)
#     print(f"回答内容：{answer['content']}")

app = FastAPI()

@app.get("/home")
async def home():
    return {"message": "Welcome to the RAG API!"}

@app.get("/query/{query}")
async def query_llm(query: str):
    print(f"接收到查询: {query}")

    retrieved_docs, retrieved_chunks = retrieve_docs(query, index)
    answer = generate_answer(query, retrieved_docs, retrieved_chunks)

    print(f"回答内容：{answer['content']}")
    message = f"回答内容：{answer['content']}"
    return {"message": message}

if __name__ == "__main__":
    index = create_faiss_index(documents)
    uvicorn.run(app, host="0.0.0.0", port=8000)   
