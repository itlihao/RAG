import re

# 文档分块函数
def chunk_document(text, max_chars=500, overlap=100):
    """
    将长文档切分成较小的块，使用滑动窗口确保上下文连贯性
    
    参数:
        text: 要切分的文本
        max_chars: 每个块的最大字符数
        overlap: 相邻块之间的重叠字符数
    
    返回:
        chunks: 切分后的文本块列表
    """
    # 如果文本长度小于最大长度，直接返回
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        # 确定当前块的结束位置
        end = start + max_chars
        
        # 如果没有到达文本末尾，尝试在句子边界切分
        if end < len(text):
            # 在结束位置查找最近的句子结束标记
            sentence_ends = [
                m.end() for m in re.finditer(r'[。！？.!?]\s*', text[start:end])
            ]
            
            if sentence_ends:  # 如果找到句子结束标记，在最后一个句子结束处切分
                end = start + sentence_ends[-1]
            else:  # 如果没有找到，尝试在单词或标点处切分
                last_space = text[start:end].rfind(' ')
                last_punct = max(text[start:end].rfind('，'), text[start:end].rfind(','))
                cut_point = max(last_space, last_punct)
                
                if cut_point > 0:  # 如果找到了合适的切分点
                    end = start + cut_point + 1
        
        # 添加当前块到结果列表
        chunks.append(text[start:end])
        
        # 移动开始位置，考虑重叠
        start = end - overlap
        
        # 确保开始位置不会后退
        if start < 0:
            start = 0
        
        # 避免无限循环
        if start >= len(text):
            break
    
    return chunks