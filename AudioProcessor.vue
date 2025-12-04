<template>
  <div class="audio-processor-container">
    <div class="header">
      <h1>音频处理系统</h1>
      <p class="subtitle">上传WAV文件，输入文本，生成音频</p>
    </div>

    <div class="main-content">
      <!-- 左侧：文件上传 -->
      <div class="section upload-section">
        <h2>1. 上传WAV文件</h2>
        <div 
          class="upload-area"
          @dragover.prevent="onDragOver"
          @dragleave.prevent="onDragLeave"
          @drop.prevent="onDrop"
          :class="{ 'drag-over': isDragOver }"
          @click="triggerFileInput"
        >
          <div class="upload-content">
            <svg class="upload-icon" viewBox="0 0 24 24">
              <path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z"/>
            </svg>
            <p class="upload-text">
              {{ uploadedFile ? uploadedFile.name : '点击或拖拽WAV文件到这里' }}
            </p>
            <p class="upload-hint">支持 .wav 格式文件</p>
          </div>
          <input 
            type="file" 
            ref="fileInput"
            @change="handleFileSelect"
            accept=".wav"
            class="file-input"
          />
        </div>

        <!-- 已上传文件预览 -->
        <div v-if="uploadedFile" class="file-preview">
          <div class="file-info">
            <span class="file-name">{{ uploadedFile.name }}</span>
            <span class="file-size">{{ formatFileSize(uploadedFile.size) }}</span>
            <button @click="removeFile" class="remove-btn">移除</button>
          </div>
          
          <!-- 显示上传成功的路径 -->
          <div v-if="uploadedFilePath" class="file-path">
            <small>路径: {{ uploadedFilePath }}</small>
          </div>
          
          <div class="audio-preview" v-if="uploadedAudioUrl">
            <audio :src="uploadedAudioUrl" controls class="audio-player"></audio>
          </div>
        </div>

        <!-- 上传进度 -->
        <div v-if="uploadProgress > 0" class="progress-container">
          <div class="progress-bar">
            <div 
              class="progress-fill" 
              :style="{ width: uploadProgress + '%' }"
            ></div>
          </div>
          <span class="progress-text">{{ uploadProgress }}%</span>
        </div>

        <button 
          @click="uploadFile" 
          :disabled="!uploadedFile || isUploading"
          class="upload-btn"
        >
          {{ isUploading ? '上传中...' : '上传文件' }}
        </button>
      </div>

      <!-- 中间：文本输入 -->
      <div class="section text-section">
        <h2>2. 输入处理文本</h2>
        <div class="text-input-container">
          <textarea 
            v-model="inputText"
            placeholder="请输入要处理的文本内容..."
            class="text-input"
            rows="6"
            maxlength="1000"
          ></textarea>
          <div class="text-counter">
            <span>{{ inputText.length }}</span>/1000 字符
          </div>
        </div>

        <button 
          @click="sendTextToBackend" 
          :disabled="!inputText.trim() || isProcessing || !uploadedFilePath"
          class="process-btn"
        >
          {{ isProcessing ? '处理中...' : uploadedFilePath ? '发送文本到后端处理' : '请先上传音频' }}
        </button>
        
        <!-- 任务状态显示 -->
        <div v-if="currentTaskId" class="task-info">
          <p>任务ID: {{ currentTaskId }}</p>
          <p>状态: {{ taskStatus }}</p>
        </div>
      </div>

      <!-- 右侧：生成的音频 -->
      <div class="section result-section">
        <h2>3. 生成的音频</h2>
        <div class="result-container" v-if="generatedAudio">
          <div class="audio-result">
            <div class="audio-info">
              <h3>{{ generatedAudio.filename }}</h3>
              <p class="audio-meta">生成时间: {{ formatDate(generatedAudio.created_at) }}</p>
            </div>
            <audio 
              :src="generatedAudio.url" 
              controls 
              class="audio-player result-audio"
              @play="onAudioPlay"
              @pause="onAudioPause"
              ref="audioPlayer"
            ></audio>
            <div class="audio-actions">
              <button @click="downloadAudio" class="action-btn download-btn">
                下载音频
              </button>
              <button @click="toggleAudio" class="action-btn play-btn">
                {{ isPlaying ? '停止播放' : '播放音频' }}
              </button>
              <button @click="clearResult" class="action-btn clear-btn">
                清除结果
              </button>
            </div>
          </div>
        </div>
        
        <div v-else class="empty-result">
          <svg class="audio-icon" viewBox="0 0 24 24">
            <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79 4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
          </svg>
          <p>生成的音频将显示在这里</p>
        </div>

        <!-- 处理状态 -->
        <div v-if="processingStatus" class="status-container">
          <div class="status-message" :class="statusClass">
            {{ processingStatus }}
          </div>
        </div>
      </div>
    </div>

    <!-- 系统状态 -->
    <div class="system-status">
      <div class="status-item">
        <span class="status-label">后端连接:</span>
        <span class="status-value" :class="{ 'connected': isConnected }">
          {{ isConnected ? '已连接' : '未连接' }}
        </span>
      </div>
      <div class="status-item">
        <span class="status-label">上传文件夹:</span>
        <span class="status-value">voice_and_output</span>
      </div>
      <div class="status-item">
        <span class="status-label">参考音频:</span>
        <span class="status-value" :class="{ 'has-audio': uploadedFilePath }">
          {{ uploadedFilePath ? '已上传' : '未上传' }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

// API基础URL
const API_BASE_URL = 'http://localhost:8000'

// 响应式数据
const uploadedFile = ref(null)
const uploadedFilePath = ref('') // 保存上传成功的音频路径
const uploadedAudioUrl = ref('')
const inputText = ref('')
const isDragOver = ref(false)
const isUploading = ref(false)
const isProcessing = ref(false)
const isPlaying = ref(false)
const uploadProgress = ref(0)
const processingStatus = ref('')
const generatedAudio = ref(null)
const isConnected = ref(false)
const fileInput = ref(null)
const audioPlayer = ref(null)
const currentTaskId = ref('')
const taskStatus = ref('')
const statusPollingInterval = ref(null)

// 检查后端连接
const checkBackendConnection = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, { timeout: 5000 })
    const data = await response.json()
    isConnected.value = response.ok && data.gpt_sovits_status === 'available'
    if (!isConnected.value) {
      console.warn('GPT-SoVITS API不可用:', data)
    }
  } catch (error) {
    console.error('后端连接失败:', error)
    isConnected.value = false
  }
}

// 处理拖拽事件
const onDragOver = () => {
  isDragOver.value = true
}

const onDragLeave = () => {
  isDragOver.value = false
}

const onDrop = (event) => {
  isDragOver.value = false
  const files = event.dataTransfer.files
  if (files.length > 0) {
    handleFile(files[0])
  }
}

// 触发文件选择
const triggerFileInput = () => {
  fileInput.value.click()
}

// 处理文件选择
const handleFileSelect = (event) => {
  const file = event.target.files[0]
  if (file) {
    handleFile(file)
  }
}

// 处理文件
const handleFile = (file) => {
  if (file.type !== 'audio/wav' && !file.name.toLowerCase().endsWith('.wav')) {
    alert('请选择WAV格式的音频文件')
    return
  }
  
  uploadedFile.value = file
  
  // 创建预览URL
  if (uploadedAudioUrl.value) {
    URL.revokeObjectURL(uploadedAudioUrl.value)
  }
  uploadedAudioUrl.value = URL.createObjectURL(file)
  
  // 清除之前的文件路径
  uploadedFilePath.value = ''
}

// 移除文件
const removeFile = () => {
  uploadedFile.value = null
  uploadedFilePath.value = ''
  if (uploadedAudioUrl.value) {
    URL.revokeObjectURL(uploadedAudioUrl.value)
    uploadedAudioUrl.value = null
  }
  uploadProgress.value = 0
  processingStatus.value = ''
}

// 格式化文件大小
const formatFileSize = (bytes) => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// 上传文件到后端
const uploadFile = async () => {
  if (!uploadedFile.value) return

  isUploading.value = true
  uploadProgress.value = 0
  processingStatus.value = '正在上传文件...'

  const formData = new FormData()
  formData.append('file', uploadedFile.value)

  try {
    const response = await fetch(`${API_BASE_URL}/upload`, {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || '上传失败')
    }

    const result = await response.json()
    
    // 保存上传成功的音频路径
    uploadedFilePath.value = result.output_path || result.filename
    processingStatus.value = '文件上传成功！'
    
    // 模拟上传进度
    let progress = 0
    const interval = setInterval(() => {
      progress += 20
      uploadProgress.value = Math.min(progress, 100)
      if (progress >= 100) {
        clearInterval(interval)
        setTimeout(() => {
          isUploading.value = false
          uploadProgress.value = 0
        }, 300)
      }
    }, 100)

  } catch (error) {
    console.error('上传错误:', error)
    processingStatus.value = '上传失败: ' + error.message
    isUploading.value = false
    uploadProgress.value = 0
  }
}

// 发送文本到后端
const sendTextToBackend = async () => {
  if (!inputText.value.trim()) {
    processingStatus.value = '请输入要处理的文本'
    return
  }

  // 检查是否已上传参考音频
  if (!uploadedFilePath.value) {
    processingStatus.value = '请先上传参考音频文件'
    return
  }

  isProcessing.value = true
  processingStatus.value = '正在处理文本，请稍候...'
  currentTaskId.value = ''
  taskStatus.value = ''

  try {
    const response = await fetch(`${API_BASE_URL}/process`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        text: inputText.value,
        ref_audio_path: uploadedFilePath.value,
        language: "zh"
      })
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || '处理失败')
    }

    const result = await response.json()
    currentTaskId.value = result.task_id
    taskStatus.value = result.status
    processingStatus.value = '音频生成任务已开始，正在处理...'
    
    // 启动轮询检查任务状态
    if (result.task_id) {
      checkTaskStatus(result.task_id)
    } else {
      throw new Error('未收到任务ID')
    }

  } catch (error) {
    console.error('处理错误:', error)
    processingStatus.value = '处理失败: ' + error.message
    isProcessing.value = false
    currentTaskId.value = ''
    taskStatus.value = ''
  }
}

// 轮询检查任务状态
const checkTaskStatus = async (taskId) => {
  try {
    const response = await fetch(`${API_BASE_URL}/task/${taskId}/status`)
    if (!response.ok) {
      throw new Error('获取任务状态失败')
    }
    
    const status = await response.json()
    taskStatus.value = status.status
    
    if (status.status === 'completed') {
      processingStatus.value = '音频生成成功！'
      isProcessing.value = false
      
      // 更新生成的音频信息
      if (status.output_file) {
        const filename = status.output_file.split('/').pop() || status.output_file.split('\\').pop()
        generatedAudio.value = {
          filename: filename,
          url: `${API_BASE_URL}/audio/${filename}`,
          created_at: status.completed_at || new Date().toISOString(),
          file_path: status.output_file
        }
      }
      
      // 停止轮询
      if (statusPollingInterval.value) {
        clearInterval(statusPollingInterval.value)
        statusPollingInterval.value = null
      }
      
    } else if (status.status === 'failed') {
      processingStatus.value = '音频生成失败: ' + (status.error || '未知错误')
      isProcessing.value = false
      currentTaskId.value = ''
      taskStatus.value = ''
      
      // 停止轮询
      if (statusPollingInterval.value) {
        clearInterval(statusPollingInterval.value)
        statusPollingInterval.value = null
      }
      
    } else {
      // 还在处理中，继续轮询
      processingStatus.value = `正在生成音频... (状态: ${status.status})`
      
      // 2秒后再次检查
      setTimeout(() => {
        if (currentTaskId.value === taskId) {
          checkTaskStatus(taskId)
        }
      }, 2000)
    }
    
  } catch (error) {
    console.error('检查任务状态失败:', error)
    // 如果失败，5秒后重试
    setTimeout(() => {
      if (currentTaskId.value === taskId) {
        checkTaskStatus(taskId)
      }
    }, 5000)
  }
}

// 播放/停止音频
const toggleAudio = () => {
  if (!generatedAudio.value || !audioPlayer.value) return
  
  if (isPlaying.value) {
    audioPlayer.value.pause()
  } else {
    audioPlayer.value.play()
  }
}

const onAudioPlay = () => {
  isPlaying.value = true
}

const onAudioPause = () => {
  isPlaying.value = false
}

// 下载音频
const downloadAudio = () => {
  if (generatedAudio.value) {
    const link = document.createElement('a')
    link.href = generatedAudio.value.url
    link.download = generatedAudio.value.filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }
}

// 清除结果
const clearResult = () => {
  generatedAudio.value = null
  if (audioPlayer.value) {
    audioPlayer.value.pause()
    audioPlayer.value.currentTime = 0
  }
  isPlaying.value = false
  processingStatus.value = ''
}

// 格式化日期
const formatDate = (dateString) => {
  try {
    const date = new Date(dateString)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  } catch (e) {
    return dateString
  }
}

// 计算状态类
const statusClass = computed(() => {
  const status = processingStatus.value
  if (status.includes('成功') || status.includes('完成')) return 'status-success'
  if (status.includes('失败') || status.includes('错误')) return 'status-error'
  if (status.includes('正在') || status.includes('处理中')) return 'status-processing'
  return 'status-info'
})

// 定期检查后端连接
let connectionCheckInterval = null

// 组件挂载时检查连接
onMounted(() => {
  checkBackendConnection()
  // 每30秒检查一次连接
  connectionCheckInterval = setInterval(checkBackendConnection, 30000)
})

// 组件卸载时清理
onUnmounted(() => {
  if (uploadedAudioUrl.value) {
    URL.revokeObjectURL(uploadedAudioUrl.value)
  }
  if (connectionCheckInterval) {
    clearInterval(connectionCheckInterval)
  }
  if (statusPollingInterval.value) {
    clearInterval(statusPollingInterval.value)
  }
})
</script>

<style scoped>
.audio-processor-container {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.header {
  text-align: center;
  margin-bottom: 40px;
}

.header h1 {
  font-size: 2.5rem;
  color: #2c3e50;
  margin-bottom: 8px;
}

.subtitle {
  font-size: 1.1rem;
  color: #7f8c8d;
}

.main-content {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
  margin-bottom: 40px;
}

.section {
  background: white;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  border: 1px solid #e0e0e0;
}

.section h2 {
  font-size: 1.5rem;
  color: #34495e;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 2px solid #ecf0f1;
}

/* 上传区域样式 */
.upload-area {
  border: 2px dashed #3498db;
  border-radius: 8px;
  padding: 40px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  background: #f8fafc;
  margin-bottom: 20px;
}

.upload-area:hover {
  background: #f0f7ff;
  border-color: #2980b9;
}

.upload-area.drag-over {
  background: #e3f2fd;
  border-color: #1a73e8;
  transform: scale(1.02);
}

.upload-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.upload-icon {
  width: 64px;
  height: 64px;
  fill: #3498db;
}

.upload-text {
  font-size: 1.1rem;
  color: #2c3e50;
  font-weight: 500;
}

.upload-hint {
  font-size: 0.9rem;
  color: #95a5a6;
}

.file-input {
  display: none;
}

/* 文件预览 */
.file-preview {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 16px;
  margin-top: 16px;
}

.file-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.file-name {
  font-weight: 500;
  color: #2c3e50;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  color: #7f8c8d;
  margin: 0 12px;
}

.remove-btn {
  background: #e74c3c;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: background 0.2s;
  flex-shrink: 0;
}

.remove-btn:hover {
  background: #c0392b;
}

/* 文件路径样式 */
.file-path {
  margin: 10px 0;
  padding: 8px 12px;
  background: #e8f4fc;
  border-radius: 6px;
  font-size: 0.85rem;
  color: #2c3e50;
  word-break: break-all;
  border-left: 3px solid #3498db;
}

/* 音频播放器 */
.audio-player {
  width: 100%;
  margin-top: 12px;
  border-radius: 6px;
}

/* 进度条 */
.progress-container {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 20px 0;
}

.progress-bar {
  flex: 1;
  height: 8px;
  background: #ecf0f1;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3498db, #2ecc71);
  transition: width 0.3s ease;
}

.progress-text {
  font-weight: 500;
  color: #2c3e50;
  min-width: 40px;
}

/* 任务信息 */
.task-info {
  margin-top: 16px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 6px;
  border-left: 4px solid #3498db;
}

.task-info p {
  margin: 4px 0;
  font-size: 0.9rem;
  color: #2c3e50;
}

/* 按钮样式 */
.upload-btn,
.process-btn {
  width: 100%;
  padding: 14px;
  font-size: 1rem;
  font-weight: 500;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
  margin-top: 16px;
}

.upload-btn {
  background: #3498db;
  color: white;
}

.upload-btn:hover:not(:disabled) {
  background: #2980b9;
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(41, 128, 185, 0.3);
}

.upload-btn:disabled {
  background: #bdc3c7;
  cursor: not-allowed;
  transform: none;
}

.process-btn {
  background: #2ecc71;
  color: white;
}

.process-btn:hover:not(:disabled) {
  background: #27ae60;
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(39, 174, 96, 0.3);
}

.process-btn:disabled {
  background: #bdc3c7;
  cursor: not-allowed;
  transform: none;
}

/* 文本输入 */
.text-input-container {
  position: relative;
}

.text-input {
  width: 100%;
  padding: 16px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  font-size: 1rem;
  font-family: inherit;
  resize: vertical;
  transition: border-color 0.3s;
  line-height: 1.5;
}

.text-input:focus {
  outline: none;
  border-color: #3498db;
  box-shadow: 0 0 0 3px rgba(52, 152, 219, 0.1);
}

.text-counter {
  text-align: right;
  font-size: 0.9rem;
  color: #7f8c8d;
  margin-top: 8px;
}

/* 结果区域 */
.result-container {
  background: linear-gradient(135deg, #f8fafc 0%, #f1f8ff 100%);
  border-radius: 12px;
  padding: 20px;
  border: 2px solid #e3f2fd;
}

.audio-info {
  margin-bottom: 16px;
}

.audio-info h3 {
  color: #2c3e50;
  margin-bottom: 4px;
  word-break: break-all;
}

.audio-meta {
  font-size: 0.9rem;
  color: #7f8c8d;
}

.audio-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.action-btn {
  flex: 1;
  padding: 10px;
  border: none;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.download-btn {
  background: #3498db;
  color: white;
}

.download-btn:hover {
  background: #2980b9;
  transform: translateY(-1px);
}

.play-btn {
  background: #2ecc71;
  color: white;
}

.play-btn:hover {
  background: #27ae60;
  transform: translateY(-1px);
}

.clear-btn {
  background: #95a5a6;
  color: white;
}

.clear-btn:hover {
  background: #7f8c8d;
  transform: translateY(-1px);
}

.empty-result {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  background: #f8f9fa;
  border-radius: 12px;
  border: 2px dashed #bdc3c7;
}

.audio-icon {
  width: 80px;
  height: 80px;
  fill: #bdc3c7;
  margin-bottom: 20px;
}

.empty-result p {
  color: #7f8c8d;
  font-size: 1.1rem;
}

/* 状态信息 */
.status-container {
  margin-top: 20px;
}

.status-message {
  padding: 12px 16px;
  border-radius: 8px;
  font-weight: 500;
  transition: all 0.3s ease;
}

.status-success {
  background: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.status-error {
  background: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}

.status-info {
  background: #d1ecf1;
  color: #0c5460;
  border: 1px solid #bee5eb;
}

.status-processing {
  background: #fff3cd;
  color: #856404;
  border: 1px solid #ffeaa7;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.8; }
  100% { opacity: 1; }
}

/* 系统状态 */
.system-status {
  display: flex;
  justify-content: center;
  gap: 40px;
  background: white;
  padding: 20px;
  border-radius: 12px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  flex-wrap: wrap;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-label {
  font-weight: 500;
  color: #2c3e50;
}

.status-value {
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 0.9rem;
  background: #f8f9fa;
  color: #6c757d;
}

.status-value.connected {
  background: #d4edda;
  color: #155724;
}

.status-value.has-audio {
  background: #d1ecf1;
  color: #0c5460;
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .main-content {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .result-section {
    grid-column: span 2;
  }
}

@media (max-width: 768px) {
  .audio-processor-container {
    padding: 16px;
  }
  
  .header h1 {
    font-size: 2rem;
  }
  
  .main-content {
    grid-template-columns: 1fr;
    gap: 16px;
  }
  
  .section {
    padding: 16px;
  }
  
  .system-status {
    flex-direction: column;
    gap: 16px;
  }
  
  .audio-actions {
    flex-direction: column;
  }
  
  .task-info {
    font-size: 0.8rem;
  }
}
</style>