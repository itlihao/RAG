
const { createApp } = Vue;

    // 设置API基础URL - 确保与服务器地址匹配
    const API_BASE_URL = 'http://localhost:8000';

    // 全局设置 axios 的 baseURL
    axios.defaults.baseURL = API_BASE_URL;

    // 配置marked选项
    marked.setOptions({
      highlight: function (code, lang) {
        const language = hljs.getLanguage(lang) ? lang : 'plaintext';
        return hljs.highlight(code, { language }).value;
      },
      langPrefix: 'hljs language-',
      gfm: true,
      breaks: true
    });

    createApp({
      data() {
        return {
          userInput: '',
          messages: [],
          chatHistory: [],
          isSidebarCollapsed: false,
          isRecording: false,
          recognition: null,
          speechSynthesis: window.speechSynthesis,
          speakingIndex: null, // 当前播放的消息索引
          isServerConnected: false,
          autoSpeech: true, // 默认启用自动语音播放
          currentUtterance: null, // 当前语音合成对象
          currentSessionId: null, // 当前会话ID
          webSearch: false, // 联网搜索开关，默认关闭
        };
      },
      mounted() {
        this.fetchChatHistory();
        this.initSpeechRecognition();
        this.testServerConnection();
        document.addEventListener('click', this.handleClickOutside);
      },
      beforeUnmount() {
        document.removeEventListener('click', this.handleClickOutside);
      },
      methods: {
        renderMarkdown(text) {
          if (!text) return '';
          try {
            // 处理可能的HTML实体
            const decoded = text.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
            return marked.parse(decoded);
          } catch (error) {
            console.error('Markdown解析错误:', error);
            return text;
          }
        },
        initSpeechRecognition() {
          const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
          if (SpeechRecognition) {
            this.recognition = new SpeechRecognition();
            this.recognition.lang = 'zh-CN';
            this.recognition.interimResults = true;
            this.recognition.continuous = true;  // 改为 true，持续识别

            this.recognition.onresult = (event) => {
              // 获取最新的识别结果
              const lastResultIndex = event.results.length - 1;
              const transcript = event.results[lastResultIndex][0].transcript;
              this.userInput = transcript;
              // 已注释掉自动发送逻辑
            };

            this.recognition.onerror = (event) => {
              console.error('语音识别错误:', event.error);
              this.isRecording = false;
              alert('语音识别失败，请检查麦克风或浏览器支持！');
            };

            this.recognition.onend = () => {
              // 只有当用户手动停止时，才会通过 toggleRecording 设置 isRecording = false
              // 这里不做任何操作，防止自动停止识别
              if (this.isRecording) {
                this.recognition.start();  // 自动重新开始识别
              }
            };
          } else {
            alert('您的浏览器不支持语音识别功能！');
          }
        },
        toggleRecording() {
          if (!this.recognition) return;

          if (this.isRecording) {
            this.recognition.stop();
            this.isRecording = false;
          } else {
            this.userInput = '';
            this.recognition.start();
            this.isRecording = true;
          }
        },
        toggleSpeech(text, index) {
          if (this.speakingIndex === index) {
            this.speechSynthesis.cancel();
            this.speakingIndex = null;
            this.currentUtterance = null;
          } else {
            this.speechSynthesis.cancel();
            this.speakText(text, index);
          }
        },

        speakText(text, index) {
          const utterance = new SpeechSynthesisUtterance(text);
          utterance.lang = 'zh-CN';
          utterance.onend = () => {
            this.speakingIndex = null;
            this.currentUtterance = null;
          };
          this.speechSynthesis.speak(utterance);
          this.speakingIndex = index;
          this.currentUtterance = utterance;
        },

        /**
         * 异步获取聊天历史记录
         *
         * @returns 无返回值
         */
        async fetchChatHistory() {
          try {
            const response = await axios.get('api/chat/history');
            this.chatHistory = response.data.data;
            console.log("聊天历史:", response.chatHistory);
            console.log("sumy:", this.chatHistory[0].summary);

          } catch (error) {
            console.error('获取历史对话失败:', error);
            this.chatHistory = []; // 确保空数据时初始化数组
            // alert('获取历史对话失败！');
          }
        },
        /**
         * 异步加载会话信息
         *
         * @param sessionId 会话ID
         * @returns 无返回值
         */
        async loadSession(sessionId) {
          try {
            const response = await axios.get(`api/chat/session/${sessionId}`);
            this.messages = response.data.messages;
            this.currentSessionId = sessionId; // 设置当前会话ID
            this.$nextTick(() => {
              this.$refs.chatContainer.scrollTop = this.$refs.chatContainer.scrollHeight;
            });
          } catch (error) {
            console.error('加载对话失败:', error);
            alert('加载对话失败！');
          }
        },
        async sendMessage() {
          if (!this.userInput.trim()) return;

          const userMessage = this.userInput;
          this.messages.push({ role: 'user', content: userMessage });
          this.userInput = '';
          this.messages.push({ role: 'bot', content: '正在思考...' });

          try {
            const botMessageIndex = this.messages.length - 1;

            // 清除"正在思考..."提示
            this.messages[botMessageIndex].content = '';

            // 重置语音相关状态
            this.speechSynthesis.cancel();
            this.currentUtterance = null;

            // 构建API URL，如果有会话ID则添加到查询参数中
            let apiUrl = `${API_BASE_URL}/api/stream?query=${encodeURIComponent(userMessage)}`;
            if (this.currentSessionId) {
              apiUrl += `&session_id=${this.currentSessionId}`;
            }

            // 添加联网搜索参数
            if (this.webSearch) {
              apiUrl += `&web_search=true`;
            }

            // 使用 EventSource API 处理 SSE
            const eventSource = new EventSource(apiUrl);

            eventSource.onmessage = (event) => {
              try {
                const data = JSON.parse(event.data);

                // 检查是否收到完成信号
                if (data.done) {
                  eventSource.close();

                  // 保存会话ID
                  if (data.session_id) {
                    this.currentSessionId = data.session_id;
                    console.log("会话ID:", this.currentSessionId);
                  }

                  // 当收到完整响应后再播放语音
                  if (this.autoSpeech) {
                    const botMessage = this.messages[botMessageIndex].content;
                    if (botMessage && botMessage.trim()) {
                      this.speakText(botMessage, botMessageIndex);
                    }
                  }

                  // 当消息完成时，应用代码高亮
                  this.$nextTick(() => {
                    document.querySelectorAll('pre code').forEach((block) => {
                      hljs.highlightElement(block);
                    });
                  });

                  // 更新聊天历史
                  // this.fetchChatHistory();

                  return;
                }

                // 处理常规消息
                if (data.content) {
                  this.messages[botMessageIndex].content += data.content;
                  console.log("收到内容块:", data.content);

                  // 如果收到会话ID但尚未设置，则保存它
                  if (data.session_id && !this.currentSessionId) {
                    this.currentSessionId = data.session_id;
                  }

                  // 滚动到底部
                  this.$nextTick(() => {
                    this.$refs.chatContainer.scrollTop = this.$refs.chatContainer.scrollHeight;
                  });
                }
              } catch (e) {
                console.error('解析响应数据失败:', e, event.data);
              }
            };

            eventSource.onerror = (error) => {
              console.error('SSE错误:', error);
              eventSource.close();

              // 如果没有收到内容
              if (!this.messages[botMessageIndex].content) {
                this.messages[botMessageIndex].content = '服务器连接错误，请稍后再试';
              }
            };

          } catch (error) {
            console.error('发送消息错误:', error);
            this.messages[this.messages.length - 1].content = `错误: ${error.message}`;
          }
        },
        
        /**
         * 切换侧边栏的显示状态。
         *
         * 如果侧边栏当前是展开的，则将其折叠；
         * 如果侧边栏当前是折叠的，则将其展开。
         */
        switchSidebar() {
          this.isSidebarCollapsed = !this.isSidebarCollapsed;
        },
        /**
         * 开始新的聊天会话
         *
         * 清空当前对话，清除当前会话ID，关闭当前正在播放的语音
         */
        startNewChat() {
          // 清空当前对话
          this.messages = [];
          // 清除当前会话ID
          this.currentSessionId = null;
          // 关闭当前正在播放的语音
          this.speechSynthesis.cancel();
          this.speakingIndex = null;
        },
        /**
         * 测试服务器连接。
         *
         * @returns 无返回值。
         */
        async testServerConnection() {
          try {
            console.log('测试服务器连接...');
            const response = await fetch(`${API_BASE_URL}/health`);

            if (response.ok) {
              console.log('服务器连接正常:', await response.json());
              this.isServerConnected = true;
              this.messages.push({
                role: 'bot',
                content: '服务器连接正常，您可以开始对话。'
              });

              // 自动播放服务器连接成功的提示
              if (this.autoSpeech) {
                this.$nextTick(() => {
                  const index = this.messages.length - 1;
                  // 使用常规播放方式，因为这不是流式输出
                  this.speakText(this.messages[index].content, index);
                });
              }
            } else {
              console.error('服务器连接异常:', response.status);
              this.messages.push({
                role: 'bot',
                content: `服务器连接异常(${response.status})，请检查服务器是否启动。`
              });
            }
          } catch (error) {
            console.error('无法连接到服务器:', error);
            this.messages.push({
              role: 'bot',
              content: `无法连接到服务器: ${error.message}。请确保服务器已启动且地址正确。`
            });
          }
        },
        /**
         * 格式化时间
         *
         * @param timestamp 时间戳字符串
         * @returns 格式化后的时间字符串
         */
        formatTime(timestamp) {
          if (!timestamp) return '';

          const date = new Date(timestamp.replace(/-/g, '/'));
          const now = new Date();
          const diffDays = Math.floor((now - date) / (24 * 60 * 60 * 1000));

          if (diffDays === 0) {
            // 今天 - 显示时间
            return '今天 ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
          } else if (diffDays === 1) {
            // 昨天
            return '昨天 ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
          } else if (diffDays < 7) {
            // 一周内 - 显示星期几
            const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
            return '星期' + weekdays[date.getDay()];
          } else {
            // 更早 - 显示完整日期
            return date.toLocaleDateString('zh-CN');
          }
        },
        /**
         * 处理点击事件，如果点击发生在下拉菜单外部，则关闭所有下拉菜单
         *
         * @param {MouseEvent} event - DOM 事件对象
         */
        handleClickOutside(event) {
          const dropdowns = document.querySelectorAll('.dropdown-menu');
          let isClickInside = false;
          dropdowns.forEach(dropdown => {
            if (dropdown.contains(event.target)) {
              isClickInside = true;
            }
          });
          if (!isClickInside) {
            this.chatHistory = this.chatHistory.map(session => ({
              ...session,
              showDropdown: false
            }));
          }
        },
        toggleDropdown(sessionId) {
          this.chatHistory = this.chatHistory.map(session => {
            if (session.id === sessionId) {
              session.showDropdown = !session.showDropdown;
            } else {
              session.showDropdown = false;
            }
            return session;
          });
        },

        exportSession(sessionId) {
          try {
            const link = document.createElement('a');
            link.href = `${API_BASE_URL}/api/chat/export/${sessionId}`;
            link.download = `session_${sessionId}.md`; // 设置下载文件名
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
          } catch (error) {
            console.error('导出会话失败:', error);
            alert('导出会话失败！');
          }
        },

        deleteSession(sessionId) {
          if (confirm('确认是否要删除?')) {
            this.chatHistory = this.chatHistory.filter(session => session.id !== sessionId);
            try {
              axios.delete(`/api/chat/session/${sessionId}`);
            } catch (error) {
              console.error('删除服务器失败:', error);
              alert('删除服务器失败！');
            }
          }
        },
        renameSession(sessionId) {
          // 获取当前会话的summary ,放到prompt中
          const currentSummary = this.chatHistory.find(session => session.id === sessionId).summary;
          const newName = prompt('Enter new name for the session:', currentSummary);
          if (newName) {
            const session = this.chatHistory.find(session => session.id === sessionId);
            if (session) {
              session.summary = newName;
              axios.post(`/api/chat/session/${sessionId}/summary`, { summary: newName });
            }
          }
        }
      },
    }).mount('#app');