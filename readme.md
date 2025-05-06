# RAG项目

## 环境配置

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
source .venv/bin/activate  # Linux/Mac
# 或

# 激活虚拟环境（Windows）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
# .venv\Scripts\activate  # Windows
# 注意：修改执行策略后建议恢复默认设置
Set-ExecutionPolicy Restricted -Scope CurrentUser

# 更新pip
pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt
```

## 运行应用

```bash
python main1.py
```

## 脚本说明

### 检索增强生成 (RAG) 脚本

- **main1.py**:  

- **main2.py**: 改进版RAG，引入了文档分块功能，通过滑动窗口确保上下文连贯性。可更好地处理较长文档，提高检索准确性。

- **main3.py**: 高级RAG，支持从文件系统加载多种格式文档(TXT/PDF/DOCX/Excel等)，实现完整的RAG知识库问答系统。

### 工具脚本

- **file_utils.py**: 文件处理工具库，支持读取多种格式文档(TXT/PDF/DOCX/MD/Excel)，提供文本清理和文档管理功能。

- **fastapi_demo.py**: FastAPI Web框架演示，可用于将RAG系统包装为Web服务API。

- **ai_test.py**: 简单的大模型API调用示例，用于测试模型连接和基本对话功能。

## 开发工具

### SQLite工具
推荐使用 Navicat Premium Lite（免费版）  
下载地址：https://www.navicat.com.cn/download/navicat-premium-lite


/bin/zsh -c "$(curl -fsSL https://gitee.com/cunkai/HomebrewCN/raw/master/Homebrew.sh)"
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install node

<div class="floating-btn">
      <button v-if="isSidebarCollapsed" class="toggle-btn" @click="switchSidebar">
        <img src="img/sidebar.png" class="slide-switch-icon">
      </button>
    </div>