// 主应用逻辑 
let currentTool = 'lane'; 
let activeTab = 'online'; 
let isConnected = false; 
let videoStream = null; 

// 绘图相关变量 
let isDrawing = false; 
let videoNaturalWidth = 0; 
let videoNaturalHeight = 0; 
let lanes = []; 
let triggers = []; 
let selectedItem = null; 
let currentLane = null; 
let currentTrigger = null; 

let dragStart = null; 
let dragTarget = null; 

// 视频相关变量 
let videoPlayer = document.getElementById('videoPlayer'); 
let drawCanvas = document.getElementById('drawCanvas'); 
let overlayCanvas = document.getElementById('overlayCanvas'); 
let ctx = drawCanvas.getContext('2d'); 
let overlayCtx = overlayCanvas.getContext('2d'); 

// API基础URL 
const API_BASE_URL = 'http://localhost:5000/api'; 
// 后端根地址（用于 /video_feed 等非 /api 路由） 
const BACKEND_ORIGIN = API_BASE_URL.replace(/\/api\/?$/, ''); 

window.BACKEND_ORIGIN = BACKEND_ORIGIN; 

// 定期更新统计数据 
let statsUpdateInterval = null; 


// 初始化画布 
function initializeCanvas() { 
    resizeCanvas(); 
    window.addEventListener('resize', resizeCanvas); 
    videoPlayer.addEventListener('load', () => { 
        // 当图片加载完成时更新实际尺寸 
        if (videoPlayer.naturalWidth > 0 && videoPlayer.naturalHeight > 0) { 
            videoNaturalWidth = videoPlayer.naturalWidth; 
            videoNaturalHeight = videoPlayer.naturalHeight; 
            resizeCanvas(); 
        } 
    }); 
    videoPlayer.addEventListener('loadedmetadata', resizeCanvas); 
} 

// 调整画布大小 
function resizeCanvas() { 
    drawCanvas.width = videoPlayer.offsetWidth; 
    drawCanvas.height = videoPlayer.offsetHeight; 
    overlayCanvas.width = videoPlayer.offsetWidth; 
    overlayCanvas.height = videoPlayer.offsetHeight; 
    
    // 更新视频实际尺寸 
    if (videoPlayer.naturalWidth > 0 && videoPlayer.naturalHeight > 0) {
        videoNaturalWidth = videoPlayer.naturalWidth;
        videoNaturalHeight = videoPlayer.naturalHeight; 
    } 
    
    redrawAll(); 
} 


// 初始化事件监听器  
function initializeEventListeners() { 
    // 数据源设置 
    document.getElementById('onlineTab').addEventListener('click', () => switchTab('online')); 
    document.getElementById('recordTab').addEventListener('click', () => switchTab('record')); 
    document.querySelector('#onlineTab .primary-btn')?.addEventListener('click', connect); 
    document.querySelector('#recordTab .primary-btn')?.addEventListener('click', loadRecord); 
    
    // 属性设置 
    document.getElementById('laneNumber').addEventListener('input', updateLaneProperties); 
    document.getElementById('laneName').addEventListener('input', updateLaneProperties); 
    document.getElementById('laneColor').addEventListener('input', updateLaneProperties); 
    document.getElementById('laneWidth').addEventListener('input', updateLaneProperties); 
    document.getElementById('triggerName').addEventListener('input', updateTriggerProperties); 
    document.getElementById('triggerColor').addEventListener('input', updateTriggerProperties); 
    document.getElementById('triggerWidth').addEventListener('input', updateTriggerProperties); 
} 
                
// 工具函数 
function switchTab(tab) { 
    activeTab = tab; 
    
    // 更新标签按钮状态 
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    }); 
    document.querySelector(`.tab-btn:nth-child(${tab === 'online' ? 1 : 2})`).classList.add('active');
    
    // 更新标签内容 
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(tab + 'Tab').classList.add('active'); 
} 

function setTool(tool) { 
    currentTool = tool; 
    
    // 更新工具按钮状态 
    document.querySelectorAll('.tool-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`.tool-btn:nth-child(${tool === 'lane' ? 1 : 2})`).classList.add('active'); 
} 


// 右侧数据面板（实时统计/车道/触发线）tab 切换 
function switchPanelTab(tabName) { 
    const panels = {
        stats: document.getElementById('statsPanel'), 
        lanes: document.getElementById('lanesPanel'), 
        triggers: document.getElementById('triggersPanel'), 
    }; 

    // 切换内容区 
    document.querySelectorAll('.panel-content').forEach(p => p.classList.remove('active')); 
    const activePanel = panels[tabName] || panels.stats; 
    if (activePanel) activePanel.classList.add('active'); 

    // 切换按钮高亮 
    const labelMap = { 
        stats: '实时统计数据', 
        lanes: '车道列表', 
        triggers: '触发线列表', 
    }; 
    const activeLabel = labelMap[tabName] || labelMap.stats; 

    document.querySelectorAll('.panel-tab-btn').forEach(btn => { 
        const isActive = (btn.textContent || '').trim() === activeLabel; 
        btn.classList.toggle('active', isActive); 
    }); 
} 

// 更新车道属性 
function updateLaneProperties() { 
    if (!selectedItem || selectedItem.type !== 'lane') return; 
    
    selectedItem.number = parseInt(document.getElementById('laneNumber').value); 
    selectedItem.name = document.getElementById('laneName').value || `车道${selectedItem.number}`; 
    selectedItem.color = document.getElementById('laneColor').value; 
    selectedItem.width = parseInt(document.getElementById('laneWidth').value); 
    
    redrawAll(); 
    updateUI();
} 


// 更新触发线属性 
function updateTriggerProperties() { 
    if (!selectedItem || selectedItem.type !== 'trigger') return; 
    
    selectedItem.name = document.getElementById('triggerName').value; 
    selectedItem.color = document.getElementById('triggerColor').value; 
    selectedItem.width = parseInt(document.getElementById('triggerWidth').value); 
    
    redrawAll(); 
    updateUI();
} 


// 绘制控制点 
function drawControlPoint(point, color) { 
    ctx.fillStyle = color; 
    ctx.strokeStyle = '#ffffff'; 
    ctx.lineWidth = 2; 
    ctx.beginPath(); 
    ctx.arc(point.x, point.y, 6, 0, Math.PI * 2); 
    ctx.fill(); 
    ctx.stroke(); 
} 

// 获取线段中点 
function getMidPoint(p1, p2) { 
    return { 
        x: (p1.x + p2.x) / 2, 
        y: (p1.y + p2.y) / 2 
    }; 
} 


// 绘制车道 
function drawLane(lane) { 
    // 即使只有一个点也显示 
    if (lane.points.length >= 1) { 
        // 如果车道被选中，使用红色绘制 
        const color = (selectedItem === lane) ? '#ff0000' : lane.color; 
        
        // 绘制线条 
        if (lane.points.length >= 2) { 
            ctx.strokeStyle = color; 
            ctx.lineWidth = lane.width; 
            ctx.lineCap = 'round'; 
            ctx.lineJoin = 'round'; 
            ctx.beginPath(); 
            
            lane.points.forEach((point, index) => { 
            // 将实际坐标转换为显示坐标 
            const displayPoint = actualToDisplay(point.x, point.y); 
            if (index === 0) { 
                ctx.moveTo(displayPoint.x, displayPoint.y); 
            } else { 
                ctx.lineTo(displayPoint.x, displayPoint.y); 
            } 
        }); 
            
        // 如果是已完成的车道（currentLane为null或不是当前车道），且有3个以上的点，则闭合多边形 
        if ((!currentLane || currentLane.id !== lane.id) && lane.points.length >= 3) { 
            ctx.closePath(); 
        } 
            
        ctx.stroke(); 
        } 
        
        // 绘制车道号 
        if (lane.points.length >= 2) { 
            const p1Display = actualToDisplay(lane.points[0].x, lane.points[0].y); 
            const p2Display = actualToDisplay(lane.points[lane.points.length - 1].x, lane.points[lane.points.length - 1].y); 
            const midPoint = getMidPoint(p1Display, p2Display); 
            overlayCtx.fillStyle = 'rgba(0, 0, 0, 0.7)'; 
            overlayCtx.fillRect(midPoint.x - 20, midPoint.y - 15, 40, 30); 
            overlayCtx.fillStyle = '#ffffff'; 
            overlayCtx.font = 'bold 14px Arial'; 
            overlayCtx.textAlign = 'center'; 
            overlayCtx.textBaseline = 'middle'; 
            overlayCtx.fillText(lane.number.toString(), midPoint.x, midPoint.y); 
        } 
        
        // 绘制控制点，选中项使用红色控制点 
        lane.points.forEach(point => { 
            const displayPoint = actualToDisplay(point.x, point.y); 
            drawControlPoint(displayPoint, color); 
        }); 
    } 
} 

// 绘制触发线 
function drawTrigger(trigger) { 
    // 即使只有一个点也显示 
    if (trigger.points.length >= 1) { 
        // 如果触发线被选中，使用红色绘制 
        const color = (selectedItem === trigger) ? '#ff0000' : trigger.color; 
        
        // 绘制线条 
        if (trigger.points.length >= 2) {
            ctx.strokeStyle = color; 
            ctx.lineWidth = trigger.width; 
            ctx.setLineDash([10, 5]); // 虚线样式
            ctx.lineCap = 'round'; 
            ctx.lineJoin = 'round'; 
            ctx.beginPath(); 
            
            trigger.points.forEach((point, index) => { 
                // 将实际坐标转换为显示坐标 
                const displayPoint = actualToDisplay(point.x, point.y); 
                if (index === 0) {
                ctx.moveTo(displayPoint.x, displayPoint.y); 
            } else { 
                ctx.lineTo(displayPoint.x, displayPoint.y); 
                }
            });
            
            ctx.stroke();
            ctx.setLineDash([]); // 重置为实线
                } 
        
                // 绘制触发线名称 
                if (trigger.points.length >= 2) { 
                const p1Display = actualToDisplay(trigger.points[0].x, trigger.points[0].y); 
                const p2Display = actualToDisplay(trigger.points[trigger.points.length - 1].x, trigger.points[trigger.points.length - 1].y); 
                const midPoint = getMidPoint(p1Display, p2Display); 
                overlayCtx.fillStyle = 'rgba(0, 0, 0, 0.7)'; 
                const textWidth = overlayCtx.measureText(trigger.name).width; 
                overlayCtx.fillRect(midPoint.x - textWidth/2 - 5, midPoint.y - 15, textWidth + 10, 30);
                overlayCtx.fillStyle = '#ffffff';
                overlayCtx.font = 'bold 14px Arial'; 
                overlayCtx.textAlign = 'center'; 
                overlayCtx.textBaseline = 'middle'; 
                overlayCtx.fillText(trigger.name, midPoint.x, midPoint.y); 
            } 
        
            // 绘制控制点，选中项使用红色控制点 
            trigger.points.forEach(point => { 
                const displayPoint = actualToDisplay(point.x, point.y); 
            drawControlPoint(displayPoint, color);
        });
    }
}

                // 绘制选中状态 
function drawSelection(item) {
    if (item.points.length < 2) return;
    
    ctx.strokeStyle = '#ff0000'; 
    ctx.lineWidth = item.width + 4; 
    ctx.setLineDash([5, 5]);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round'; 
    ctx.beginPath(); 
    
    item.points.forEach((point, index) => { 
        // 将实际坐标转换为显示坐标 
        const displayPoint = actualToDisplay(point.x, point.y);
        if (index === 0) {
            ctx.moveTo(displayPoint.x, displayPoint.y);
        } else {
            ctx.lineTo(displayPoint.x, displayPoint.y); 
        } 
    }); 
    
    ctx.stroke(); 
    ctx.setLineDash([]); 
} 


                                                            
// 重绘所有内容 
function redrawAll() {
    // 清空画布 
    ctx.clearRect(0, 0, drawCanvas.width, drawCanvas.height); 
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height); 
    
    // 绘制所有车道 
    lanes.forEach(lane => drawLane(lane)); 
    
    // 绘制所有触发线
    triggers.forEach(trigger => drawTrigger(trigger)); 
    
    // 绘制选中状态 
    if (selectedItem) {
        drawSelection(selectedItem);
    }
} 
    
// 更新车道列表
function updateLanesList() { 
    const lanesList = document.getElementById('lanesList'); 
    if (!lanesList) return; 
    lanesList.innerHTML = '';

lanes.forEach((lane, index) => { 
    const laneCard = document.createElement('div');
laneCard.className = 'item-card' + (selectedItem === lane ? ' selected' : '');

    laneCard.innerHTML = `
      <div class="item-info">
        <div class="item-title-row">
          <div class="item-title">${lane.name || `车道 ${lane.number}`}</div>
          <button class="delete-btn" type="button" title="删除车道" aria-label="删除车道">🗑️</button>
        </div>
        <div class="item-details">编号: ${lane.number} · ${lane.points.length} 个点</div>
      </div>
    `;

// ✅ 强制这一行横向排布（就算你CSS没生效也能顶住） 
const row = laneCard.querySelector('.item-title-row'); 
const title = laneCard.querySelector('.item-title'); 
const delBtn = laneCard.querySelector('.delete-btn'); 
    if (row) {
      row.style.display = 'flex';
    row.style.alignItems = 'center'; 
    row.style.justifyContent = 'space-between'; 
    row.style.gap = '8px'; 
} 
if (title) { 
    title.style.flex = '1'; 
    title.style.minWidth = '0'; 
    title.style.whiteSpace = 'nowrap'; 
    title.style.overflow = 'hidden'; 
    title.style.textOverflow = 'ellipsis';
} 
if (delBtn) { 
    delBtn.style.flex = '0 0 auto'; 
    delBtn.style.background = 'transparent'; 
    delBtn.style.border = 'none'; 
    delBtn.style.cursor = 'pointer'; 
    delBtn.style.padding = '2px 6px'; 
    delBtn.style.lineHeight = '1';
 }

    // 点击卡片选择（点删除不触发）
    laneCard.addEventListener('click', (e) => { 
        if (e?.target?.closest?.('.delete-btn')) return;
        selectedItem = lane; 
        document.getElementById('laneProperties').style.display = 'block'; 
        document.getElementById('triggerProperties').style.display = 'none'; 
        updateUI(); 
        redrawAll(); 
    });

    // ✅ 删除：传 index（不是 lane.id）
    delBtn?.addEventListener('click', (e) => { 
        e.stopPropagation(); 
        deleteLane(index); 
    }); 

        lanesList.appendChild(laneCard); 
    }); 
} 

function updateTriggersList() { 
    const triggersList = document.getElementById('triggersList');
     if (!triggersList) return; 
    triggersList.innerHTML = ''; 

  triggers.forEach((trigger, index) => {
    const triggerCard = document.createElement('div');
        triggerCard.className = 'item-card' + (selectedItem === trigger ? ' selected' : ''); 

    triggerCard.innerHTML = `
      <div class="item-info">
        <div class="item-title-row">
          <div class="item-title">${trigger.name}</div>
          <button class="delete-btn" type="button" title="删除触发线" aria-label="删除触发线">🗑️</button>
        </div>
        <div class="item-details">${trigger.points.length} 个点</div>
      </div>
    `;

    // ✅ 强制横向排布
    const row = triggerCard.querySelector('.item-title-row');
    const title = triggerCard.querySelector('.item-title');
    const delBtn = triggerCard.querySelector('.delete-btn'); 
    if (row) {
        row.style.display = 'flex';
        row.style.alignItems = 'center'; 
        row.style.justifyContent = 'space-between';
        row.style.gap = '8px'; 
    } 
    if (title) {
        title.style.flex = '1';
        title.style.minWidth = '0'; 
        title.style.whiteSpace = 'nowrap'; 
        title.style.overflow = 'hidden'; 
        title.style.textOverflow = 'ellipsis'; 
    } 
    if (delBtn) {
        delBtn.style.flex = '0 0 auto';
        delBtn.style.background = 'transparent';
        delBtn.style.border = 'none';
        delBtn.style.cursor = 'pointer'; 
        delBtn.style.padding = '2px 6px';
        delBtn.style.lineHeight = '1';
    } 

    triggerCard.addEventListener('click', (e) => { 
        if (e?.target?.closest?.('.delete-btn')) return; 
        selectedItem = trigger; 
        document.getElementById('laneProperties').style.display = 'none'; 
        document.getElementById('triggerProperties').style.display = 'block';
        updateUI();
        redrawAll();
    });

    // ✅ 删除：传 index（不是 trigger.id）
    delBtn?.addEventListener('click', (e) => { 
        e.stopPropagation(); 
        deleteTrigger(index); 
    }); 

    triggersList.appendChild(triggerCard); 
    }); 
}


// 更新属性面板
function updatePropertiesPanel() { 
    const laneProperties = document.getElementById('laneProperties');
     const triggerProperties = document.getElementById('triggerProperties');
    
    // 添加null检查
 if (!laneProperties || !triggerProperties) { 
    console.warn('属性面板DOM元素未找到'); 
    return; 
} 
if (!selectedItem) {
        // 不重置为默认值，保持当前属性面板的值
        
        // 显示当前工具对应的属性面板
document.getElementById('laneProperties').style.display = currentTool === 'lane' ? 'block' : 'none'; 
        document.getElementById('triggerProperties').style.display = currentTool === 'trigger' ? 'block' : 'none';
        return;
 } 
    
 if (selectedItem.type === 'lane') {
        // 显示车道属性面板
document.getElementById('laneProperties').style.display = 'block'; 
document.getElementById('triggerProperties').style.display = 'none';
        
        // 更新属性值
document.getElementById('laneNumber').value = selectedItem.number; 
        document.getElementById('laneName').value = selectedItem.name || `车道${selectedItem.number}`;
 document.getElementById('laneColor').value = selectedItem.color; 
 document.getElementById('laneWidth').value = selectedItem.width;
 } else if (selectedItem.type === 'trigger') {
        // 显示触发线属性面板
document.getElementById('laneProperties').style.display = 'none'; 
document.getElementById('triggerProperties').style.display = 'block';
        
        // 更新属性值
document.getElementById('triggerName').value = selectedItem.name; 
document.getElementById('triggerColor').value = selectedItem.color; 
document.getElementById('triggerWidth').value = selectedItem.width;
    }
}

// 更新UI
function updateUI() {
    // 更新车道列表
 updateLanesList();
    
    // 更新触发线列表
updateTriggersList();
    
    // 更新属性面板
    updatePropertiesPanel();
}

// 显示通知消息
function showNotification(message, type = 'info') {
    // 移除之前的通知
const existingNotification = document.querySelector('.notification'); 
if (existingNotification) { 
    existingNotification.remove(); 
}
    
 const notification = document.createElement('div'); 
    notification.className = `notification notification-${type}`;
 notification.textContent = message;
    
    // 添加样式
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 4px;
        color: white;
        font-size: 0.9rem;
        z-index: 1000;
        max-width: 300px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        animation: slideIn 0.3s ease-out;
    `;
    
    // 根据类型设置背景色
    const colors = {
        success: '#4CAF50',
        error: '#f44336',
        warning: '#ff9800',
        info: '#2196F3'
    };
    notification.style.backgroundColor = colors[type] || colors.info;
    
    document.body.appendChild(notification);
    
    // 3秒后自动移除
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 3000);
}


// 开始定期更新统计数据
function startStatsUpdate() {
    // 清除之前的定时器
if (window.statsUpdateInterval) { 
    clearInterval(window.statsUpdateInterval); 
}
    
    // 每2秒更新一次统计数据
window.statsUpdateInterval = setInterval(updateStats, 2000); 
}


// 连接RTSP流
async function connect() { 
    const rtspUrl = document.getElementById('rtspUrl').value; 
    const cyberEventChannel = document.getElementById('cyberEventChannel').value; 
    const cyberPointcloudChannel = document.getElementById('cyberPointcloudChannel').value; 
    
    if (!rtspUrl) {
        showNotification('请输入RTSP URL', 'error');
        return;
    }

    const connectBtn = document.querySelector('#onlineTab .primary-btn'); 
    connectBtn.disabled = true;
    connectBtn.textContent = '连接中...';

    try {
        const response = await fetch(`${API_BASE_URL}/rtsp/connect`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                rtsp_url: rtspUrl,
                cyber_event_channel: cyberEventChannel,
                cyber_pointcloud_channel: cyberPointcloudChannel
            })
        });
        const data = await response.json();
        
        if (data.success) {
            isConnected = true;
            startVideoStream();

            // 启动点云图片流
            if(cyberPointcloudChannel && cyberPointcloudChannel.trim() !== ''){
                startPointCloudImageStream();
                showNotification('点云流已启动', 'success');
            }

            try {
                updateConnectionStatus(true, 'RTSP 已建立');
            } catch (uiErr) {
                console.error('连接成功，但 UI 更新失败:', uiErr);
                showNotification('连接成功，但界面更新失败（不影响连接）', 'warning');
            }
            showNotification('连接成功！', 'success');
        } else {
            try {
                updateConnectionStatus(false, '连接失败');
            } catch (_) {}
            throw new Error(data.message || '连接失败');
        }

    } catch (error) {
        console.error('连接错误:', error);
        updateConnectionStatus(false, '连接失败');
        alert('连接失败: ' + error.message);
    } finally {
        connectBtn.disabled = false;
        connectBtn.textContent = '连接';
    }
}

//加载Record文件 - 打开channel选择弹窗 
async function loadRecord() { 
    const fileInput = document.getElementById('recordFile'); 
    if (fileInput.files.length === 0) { 
        alert('请选择记录文件'); 
        return; 
    } 
    const formData = new FormData(); 
    formData.append('record_file', fileInput.files[0]); 
    const loadBtn = document.querySelector('#recordTab .primary-btn'); 
    loadBtn.disabled = true; 
    loadBtn.textContent = '加载中...'; 
    try { 
        const response = await fetch(`${API_BASE_URL}/record/load`, { 
            method: 'POST', 
            body: formData 
        }); 
        const data = await response.json(); 
        if (data.success && data.channels) {
            //打开channel选择弹窗 
            openChannelSelectModal(data.channels, fileInput.files[0]); 
        } else { 
            console.error('API返回数据格式不正确:', data); 
            throw new Error(data.message || '加载失败'); 
        } 
    } catch (error) { 
            console.error('加载错误:', error); 
            alert('加载失败: ' + error.message); 
    } finally { 
        loadBtn.disabled = false; 
        loadBtn.textContent = '加载'; 
    } 
} 

let currentRecordFile = null; 

function openChannelSelectModal(channels, file) { 
    currentRecordFile = file; 
    const cameraSelect = document.getElementById('cameraChannel'); 
    const eventSelect = document.getElementById('eventChannel'); 
    const boxSelect = document.getElementById('boxChannel'); 
    const pointsSelect = document.getElementById('pointsChannel'); 
    if (!cameraSelect || !eventSelect || !boxSelect || !pointsSelect) { 
        console.error('无法找到channel选择下拉框元素'); 
        return; 
    }
    //清空选项 
    const resetOptions = (selectEl) => { 
        selectEl.innerHTML = '<option value="">-- 选择 --</option>'; 
    }; 
    resetOptions(cameraSelect); 
    resetOptions(eventSelect); 
    resetOptions(boxSelect); 
    resetOptions(pointsSelect);
    //填充选项 
    for (const [name, type] of Object.entries(channels)) { 
        const option = document.createElement('option'); 
        option.value = name; 
        option.textContent = name; 
        if (type === 'camera') { 
            cameraSelect.appendChild(option); 
        } else if (type === 'event') { 
            eventSelect.appendChild(option); 
        } else if (type === 'box') { 
            boxSelect.appendChild(option); 
        } else if (type === 'points') { 
            pointsSelect.appendChild(option); 
        } }
    //设置默认值 
    setDefaultChannel(cameraSelect, channels, 'camera'); 
    setDefaultChannel(eventSelect, channels, 'event'); 
    setDefaultChannel(boxSelect, channels, 'box'); 
    setDefaultChannel(pointsSelect, channels, 'points');
    //显示弹窗：只加一个 
    const modal = document.getElementById('channelSelectModal'); 
    if (modal) { 
        modal.classList.add('is-open'); 
    } 
} 

function setDefaultChannel(selectElement, channels, type) { 
    for (const [name, channelType] of Object.entries(channels)) { 
        if (channelType === type) { 
            selectElement.value = name; 
            return; 
        } 
    } 
} 

function closeChannelSelectModal() { 
    const modal = document.getElementById('channelSelectModal'); 
    if (modal) { 
        modal.classList.remove('is-open'); 
    } 
    currentRecordFile = null; 
}

// 启动视频流 
function startVideoStream() { 
    const videoPlayer = document.getElementById('videoPlayer'); 
    if (!videoPlayer) { 
        console.warn('[startVideoStream] #videoPlayer not found'); 
        return; 
    }

    // 清除之前的视频流 
    videoPlayer.src = '';

    // 添加错误处理 
    videoPlayer.onerror = function () { 
    console.error('视频流加载错误');
    showNotification('视频流加载失败，请检查连接', 'error');
  };

  // 可选：更容易看日志
  videoPlayer.onloadstart = function () {
    console.log('开始加载视频流');
    showNotification('正在加载视频流...', 'info');
  };

  videoPlayer.onloadeddata = function () {
    console.log('视频流加载完成');
    showNotification('视频流加载完成', 'success');
  };

  const url = `${BACKEND_ORIGIN}/video_feed?ts=${Date.now()}`;
  console.log('[startVideoStream] video url =', url);

  videoPlayer.src = url;
  videoStream = url;
}


// 更新连接状态显示
function updateConnectionStatus(connected, detailText = '') {
  // 顶部状态（你 HTML 里已有）
const top = document.getElementById('connectionStatus');
 if (top) top.textContent = connected ? '已连接' : '未连接';

  // 在线 tab 按钮下状态
const row = ensureOnlineStatusRow(); 
if (!row) return; 

const dot = document.getElementById('onlineConnectionStatusDot'); 
const text = document.getElementById('onlineConnectionStatusText'); 

const baseText = connected ? '已连接' : '未连接'; 
  const fullText = detailText ? `${baseText}（${detailText}）` : baseText;

  if (text) text.textContent = fullText;

  // 不指定颜色也行；如果你不介意小小配色，这里更直观
  if (dot) dot.style.color = connected ? '#1a7f37' : '#999';
}

function ensureOnlineStatusRow() {
  // 连接按钮（在线 tab 里的 primary-btn）
const btn = document.querySelector('#onlineTab .primary-btn'); 
  if (!btn) {
    console.warn('[ensureOnlineStatusRow] connect button not found');
    return null;
  }

  // 已创建过就直接返回
  let row = document.getElementById('onlineConnectionStatusRow');
  if (row) return row;

  // 创建一行：● + 文本
row = document.createElement('div'); 
  row.id = 'onlineConnectionStatusRow';
  row.style.marginTop = '8px';
  row.style.display = 'flex';
  row.style.alignItems = 'center';
  row.style.gap = '8px';
  row.style.fontSize = '13px';
  row.style.color = '#666';

  const dot = document.createElement('span');
  dot.id = 'onlineConnectionStatusDot';
  dot.textContent = '●';
  dot.style.fontSize = '12px';

  const text = document.createElement('span');
  text.id = 'onlineConnectionStatusText';
  text.textContent = '未连接';

  row.appendChild(dot);
  row.appendChild(text);

  // 插到按钮下面
  const parent = btn.parentNode;
  parent.insertBefore(row, btn.nextSibling);

  return row;
}



// 获取车道配置
function getLanesConfig() {
    console.log('获取车道配置');
    return lanes.map(lane => ({
        ...lane,
        points: lane.points.map(p => ({ x: p.x, y: p.y }))
    }));
}

// 获取触发线配置
function getTriggersConfig() {
    console.log('获取触发线配置');
    return triggers.map(trigger => ({
        ...trigger,
        points: trigger.points.map(p => ({ x: p.x, y: p.y }))
    }));
}


// 保存配置
async function saveConfig() {
    try {
const config = {
            lanes: getLanesConfig(),
                    triggers: getTriggersConfig(),
                    videoSize: {
                        width: videoNaturalWidth,
                        height: videoNaturalHeight
                    }
        };

        const response = await fetch(`${API_BASE_URL}/config/save`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(config)
        });

        const data = await response.json();
        
        if (data.success) {
            alert('配置保存成功！');
        } else {
            throw new Error(data.message || '保存失败');
        }
    } catch (error) {
        console.error('保存配置错误:', error);
        alert('保存配置失败: ' + error.message);
    } 
}

// 应用配置到界面
function applyConfig(config) {
    console.log('应用配置:', config);
    
    try {
        // 应用车道配置
if (config.lanes && Array.isArray(config.lanes)) {
            // 清空现有车道
lanes = [];
            
            // 添加新车道
            config.lanes.forEach((lane, idx) => {
                const newLane = {
                    ...lane,
                    name: lane.name || `车道${lane.number || idx + 1}`,
                    // 确保points数组存在且格式正确
                    points: (lane.points || []).map(p => ({ x: p.x, y: p.y }))
                };
                lanes.push(newLane);
            });
            
            console.log('应用车道配置:', lanes);
        }
        
        // 应用触发线配置
if (config.triggers && Array.isArray(config.triggers)) {
            // 清空现有触发线
triggers = [];
            
            // 添加新触发线
            config.triggers.forEach(trigger => {
                const newTrigger = {
                    ...trigger,
                    // 确保points数组存在且格式正确
                    points: (trigger.points || []).map(p => ({ x: p.x, y: p.y }))
                };
                triggers.push(newTrigger);
            });
            
            console.log('应用触发线配置:', triggers);
        }
        
        // 如果配置中有视频尺寸信息，且当前视频尺寸为0，尝试使用配置中的尺寸
        if (config.videoSize && videoNaturalWidth === 0 && videoNaturalHeight === 0) {
            videoNaturalWidth = config.videoSize.width;
            videoNaturalHeight = config.videoSize.height;
            console.log('使用配置中的视频尺寸:', config.videoSize);
        }
        
        // 清除选中状态
        selectedItem = null;
        currentLane = null;
        currentTrigger = null;
        
        // 重新绘制所有内容
        redrawAll();
        
        // 更新UI显示
        updateUI();
        
        // 更新配置显示
        updateConfigDisplay(config);
        
        console.log('配置应用成功');
        
    } catch (error) {
        console.error('应用配置失败:', error);
        alert('应用配置失败: ' + error.message);
    }
}

// 更新配置显示
function updateConfigDisplay(config) {
    const lanesContainer = document.getElementById('lanesContainer');
    const triggersContainer = document.getElementById('triggersContainer');
    
    // 更新车道列表显示
    if (lanesContainer) {
        if (config.lanes && config.lanes.length > 0) {
            let lanesHtml = '';
            config.lanes.forEach((lane, index) => {
                lanesHtml += `
                    <div class="config-item">
                        <span class="config-label">${lane.name || `车道${lane.number || index + 1}`}</span>
                        <div class="config-actions">
                            <button class="config-btn edit-btn" onclick="editLane(${index})">编辑</button>
                            <button class="config-btn delete-btn" onclick="deleteLane(${index})">删除</button>
                        </div>
                    </div>
                `;
            });
            lanesContainer.innerHTML = lanesHtml;
        } else {
            lanesContainer.innerHTML = '<div class="config-item"><span class="config-label">暂无车道配置</span></div>';
        }
    }
    
    // 更新触发线列表显示
    if (triggersContainer) {
        if (config.triggers && config.triggers.length > 0) {
            let triggersHtml = '';
            config.triggers.forEach((trigger, index) => {
                triggersHtml += `
                    <div class="config-item">
                        <span class="config-label">${trigger.name || `触发线${index + 1}`}</span>
                        <div class="config-actions">
                            <button class="config-btn edit-btn" onclick="editTrigger(${index})">编辑</button>
                            <button class="config-btn delete-btn" onclick="deleteTrigger(${index})">删除</button>
                        </div>
                    </div>
                `;
            });
            triggersContainer.innerHTML = triggersHtml;
        } else {
            triggersContainer.innerHTML = '<div class="config-item"><span class="config-label">暂无触发线配置</span></div>';
        }
    }
}


// 编辑车道
function editLane(index) {
    if (index >= 0 && index < lanes.length) {
        selectedItem = lanes[index];
        updateUI();
        console.log('编辑车道:', selectedItem);
    } else {
        console.warn('无效的车道索引:', index);
    }
}


function deleteLane(index) {
  if (index < 0 || index >= lanes.length) {
    console.warn('无效的车道索引:', index);
    return;
  }
  const removed = lanes[index];
  if (!confirm('确定要删除这条车道吗？')) return;

  lanes.splice(index, 1);

  if (selectedItem === removed) selectedItem = null;
  if (currentLane && currentLane.id === removed.id) currentLane = null;

  redrawAll();
  updateUI();
  if (typeof updateConfigDisplay === 'function') {
    updateConfigDisplay({ lanes, triggers });
  }
}

function deleteTrigger(index) {
  if (index < 0 || index >= triggers.length) {
    console.warn('无效的触发线索引:', index);
    return;
  }
  const removed = triggers[index];
  if (!confirm('确定要删除这条触发线吗？')) return;

  triggers.splice(index, 1);

  if (selectedItem === removed) selectedItem = null;
  if (currentTrigger && currentTrigger.id === removed.id) currentTrigger = null;

  redrawAll();
  updateUI();
  if (typeof updateConfigDisplay === 'function') {
    updateConfigDisplay({ lanes, triggers });
  }
}


// 编辑触发线
function editTrigger(index) {
    if (index >= 0 && index < triggers.length) {
        selectedItem = triggers[index];
        updateUI();
        console.log('编辑触发线:', selectedItem);
    } else {
        console.warn('无效的触发线索引:', index);
    }
}

// 加载配置
async function loadConfig() {
    try {
        const response = await fetch(`${API_BASE_URL}/config/load`);
        
        // 检查HTTP状态码
        if (!response.ok) {
            throw new Error(`HTTP错误: ${response.status} ${response.statusText}`);
        }
        
        const data = await response.json();
        
        if (data.success) {
            applyConfig(data.config);
            alert('配置加载成功！');
        } else {
            throw new Error(data.message || '加载失败');
        }
    } catch (error) {
        console.error('加载配置错误:', error);
        
        // 提供更详细的错误信息
        if (error.message.includes('Failed to fetch')) {
            alert('加载配置失败: 无法连接到后端服务，请确保后端服务已启动');
        } else if (error.message.includes('HTTP错误: 404')) {
            alert('加载配置失败: 后端API接口不存在');
        } else {
            alert('加载配置失败: ' + error.message);
        }
    }
}

// 导出数据
async function exportData() {
    // 导出时，坐标已经是实际视频尺寸的坐标，直接使用
    // 但需要添加视频尺寸信息以便后续使用
    const data = {
        lanes: lanes.map(lane => ({
            ...lane,
            points: lane.points.map(p => ({ x: p.x, y: p.y }))
        })),
        triggers: triggers.map(trigger => ({
            ...trigger,
            points: trigger.points.map(p => ({ x: p.x, y: p.y }))
        })),
        videoSize: {
            width: videoNaturalWidth,
            height: videoNaturalHeight
        },
        exportTime: new Date().toISOString()
    };

    const dataStr = JSON.stringify(data, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = 'lane_trigger_data.json';
    link.click();
    
    URL.revokeObjectURL(url);
}


function resetAnnotationsUI() {
    // 结束绘制态
    isDrawing = false;
    currentLane = null;
    currentTrigger = null;
    selectedItem = null;
    dragStart = null;
    dragTarget = null;

    // 清空标注数据
    lanes = [];
    triggers = [];

    // 立刻刷新画布与列表
    redrawAll();
    updateUI();

    // 统计面板立刻回到等待（避免等下一次 interval）
    updateStatsDisplay({});
}

// 清理资源（前端标注 + 后端连接）
async function clearAll() {
    if (!confirm('确定要清空所有触发线和车道吗？')) return;
    resetAnnotationsUI();
}

function toggleFullscreen() {
    const videoContainer = document.querySelector('.video-container');
    if (!document.fullscreenElement) {
        videoContainer.requestFullscreen?.();
    } else {
        document.exitFullscreen?.();
    }
}

// 监听全屏状态变化
document.addEventListener('fullscreenchange', handleFullscreenChange);
document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
document.addEventListener('mozfullscreenchange', handleFullscreenChange);
document.addEventListener('MSFullscreenChange', handleFullscreenChange);

function handleFullscreenChange() {
    const videoSection = document.querySelector('.video-section');
    const videoContainer = document.querySelector('.video-container');
    
    
    if (document.fullscreenElement) {
        // 进入全屏状态
        videoSection.classList.add('fullscreen');
        videoContainer.classList.add('fullscreen');
        
        // 更新全屏按钮文本
        const fullscreenBtn = document.querySelector('.video-controls .control-btn');
        fullscreenBtn.textContent = '退出全屏';
        
        // 调整视频和canvas尺寸
        adjustVideoSize();
    } else {
        // 退出全屏状态
        videoSection.classList.remove('fullscreen');
        videoContainer.classList.remove('fullscreen');
        
        // 更新全屏按钮文本
        const fullscreenBtn = document.querySelector('.video-controls .control-btn');
        fullscreenBtn.textContent = '全屏';
        
        // 恢复视频和canvas尺寸
        adjustVideoSize();
    }
}

// 调整视频和canvas尺寸
function adjustVideoSize() {
    const videoContainer = document.querySelector('.video-container');
    const videoPlayer = document.getElementById('videoPlayer');
    const drawCanvas = document.getElementById('drawCanvas');
    const overlayCanvas = document.getElementById('overlayCanvas');


    // 添加null检查
    if (!videoContainer || !videoPlayer || !drawCanvas || !overlayCanvas) {
        console.warn('视频相关DOM元素未找到，无法调整尺寸');
        return;
    }

    
    if (document.fullscreenElement) {
        // 全屏状态：使用窗口尺寸
        const width = window.innerWidth;
        const height = window.innerHeight;
        
        videoContainer.style.width = width + 'px';
        videoContainer.style.height = height + 'px';
        videoPlayer.style.width = width + 'px';
        videoPlayer.style.height = height + 'px';
        drawCanvas.width = width;
        drawCanvas.height = height;
        overlayCanvas.width = width;
        overlayCanvas.height = height;
    } else {
        // 正常状态：使用自适应高度
        const containerWidth = videoContainer.clientWidth;
        
        // 获取视频的实际比例
        const videoRatio = getVideoAspectRatio(videoPlayer);
        
        // 根据视频比例计算容器高度
        let containerHeight;
        if (videoRatio > 0) {
            containerHeight = containerWidth / videoRatio;
        } else {
            // 如果无法获取视频比例，使用默认的16:9比例
            containerHeight = containerWidth * 9 / 16;
        }
        
        // 设置容器高度，但不超过父容器可用高度
        const parentHeight = videoContainer.parentElement.clientHeight;
        const maxHeight = parentHeight - 80; // 预留空间给标题和控制按钮
        
        if (containerHeight > maxHeight) {
            containerHeight = maxHeight;
        }
        
        videoContainer.style.height = containerHeight + 'px';
        
        // 设置视频和画布尺寸
        videoPlayer.style.width = '100%';
        videoPlayer.style.height = '100%';
        drawCanvas.width = containerWidth;
        drawCanvas.height = containerHeight;
        overlayCanvas.width = containerWidth;
        overlayCanvas.height = containerHeight;
    }
}

// 获取视频的宽高比例
function getVideoAspectRatio(videoPlayer) {
    // 如果视频已加载元数据，使用实际尺寸
    if (videoPlayer.videoWidth > 0 && videoPlayer.videoHeight > 0) {
        return videoPlayer.videoWidth / videoPlayer.videoHeight;
    }
    
    // 如果视频有src属性但未加载，尝试从URL推断
    if (videoPlayer.src) {
        // 这里可以根据视频源推断比例，或者使用默认比例
        // 暂时返回0，让函数使用默认比例
        return 0;
    }
    
    return 0; // 返回0表示使用默认比例
}

// 启动点云图片流
function startPointCloudImageStream() {
    const pointcloudImage = document.getElementById('pointcloudImage');
    const pointcloudLoading = document.getElementById('pointcloudLoading');
    if (!pointcloudImage) {
        console.warn('[pointcloud] #pointcloudImage not found');
        return;
    }

    // 显示“等待点云数据...”
    if (pointcloudLoading) {
        pointcloudLoading.style.display = 'block';
    }

    const url = `${BACKEND_ORIGIN}/points?ts=${Date.now()}`;
    console.log('[pointcloud] img src =', url);

    // 新图加载出来就隐藏 loading
    pointcloudImage.onload = function () {
        if (pointcloudLoading) {
            pointcloudLoading.style.display = 'none';
        }
    };

    pointcloudImage.onerror = function (e) {
        console.error('[pointcloud] image error:', e);
        if (pointcloudLoading) {
            pointcloudLoading.style.display = 'none';
        }
    };

    // ★ 关键：直接让 <img> 播 MJPEG 流，浏览器自己处理 boundary
    pointcloudImage.src = url;
}

// 修改resize监听器
window.addEventListener('resize', function() {
    adjustVideoSize(); // 调整视频尺寸
});


// 检查后端健康状态
async function checkBackendHealth() {
    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        if (response.ok) {
            const data = await response.json();
            console.log('后端服务正常:', data);
            showNotification('后端服务已启动，可以正常使用', 'success');
        } else {
            console.warn('后端服务未就绪');
            showNotification('后端服务未启动，请先启动后端服务', 'warning');
        }
    } catch (error) {
        console.warn('无法连接到后端服务:', error);
        showNotification('后端服务未启动，请先启动后端服务', 'warning');
    }
}


// 确保只有一个DOMContentLoaded事件监听器
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}


// 更新统计数据
async function updateStats() {
  const statsContainer = document.getElementById('statsContainer');
  if (!statsContainer) return;

  if (!isConnected) {
    updateStatsDisplay({});
    return;
  }

  const url = `${API_BASE_URL}/stats?ts=${Date.now()}`;
  console.log('[updateStats] fetching:', url);

  try {
    const resp = await fetch(url, { cache: 'no-store' });

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status} ${resp.statusText}`);
    }

    const data = await resp.json();
    console.log('[updateStats] resp:', data);

    if (!data.success) {
      updateStatsDisplay({});
      return;
    }

    // 这里沿用你原来的渲染逻辑
    const stats = data.stats || {};
    statsContainer.innerHTML = '';

    if (Object.keys(stats).length === 0) {
      statsContainer.innerHTML = '<div class="stats-item"><span class="stats-label">等待数据...</span></div>';
      return;
    }

    Object.keys(stats).forEach(regionName => {
      const regionStats = stats[regionName];
      const statsItem = document.createElement('div');
      statsItem.className = 'stats-item';

      const displayName = regionName === 'total' ? '总计' : regionName;

      statsItem.innerHTML = `
        <span class="stats-label">${displayName}</span>
        <div class="stats-count">${regionStats.image_count ?? 0}</div>
        <div class="stats-subcount">事件数: ${regionStats.event_count ?? 0}</div>
      `;

      if (regionName === 'total') {
        statsItem.style.borderTop = '2px solid #4285F4';
        statsItem.style.fontWeight = 'bold';
      }

      statsContainer.appendChild(statsItem);
    });

  } catch (e) {
    console.error('[updateStats] failed:', e);
    // 出错也给用户一个可见状态（否则一直“等待数据...”很难判断）
    statsContainer.innerHTML = `<div class="stats-item"><span class="stats-label">统计请求失败：${e.message}</span></div>`;
  }
}



function updateStatsDisplay(stats) {
    const statsContainer = document.getElementById('statsContainer');
    if (!statsContainer) return;
    
    if (!stats || Object.keys(stats).length === 0) {
        statsContainer.innerHTML = '<div class="stats-item"><span class="stats-label">等待数据...</span></div>';
        return;
    }
    
    let html = '';
    Object.keys(stats).forEach(regionName => {
        const regionStats = stats[regionName];
        const displayName = regionName === 'total' ? '总计' : regionName;
        const specialStyle = regionName === 'total' ? 'style="border-top: 2px solid #4285F4; font-weight: bold;"' : '';
        
        html += `
            <div class="stats-item" ${specialStyle}>
                <span class="stats-label">${displayName}</span>
                <div class="stats-count">${regionStats.image_count || 0}</div>
                <div class="stats-subcount">事件数: ${regionStats.event_count || 0}</div>
            </div>
        `;
    });
    
    statsContainer.innerHTML = html;
}


// 数据源设置收缩/展开功能
function toggleDataSource() {
    const dataSourceBar = document.querySelector('.data-source-bar');
    const toggleBtn = document.getElementById('toggleDataSource');
    const dataSourceContent = document.getElementById('dataSourceContent');
    
    dataSourceBar.classList.toggle('collapsed');
    toggleBtn.classList.toggle('collapsed');
    
    // 更新按钮文本
    if (dataSourceBar.classList.contains('collapsed')) {
        toggleBtn.textContent = '▼';
    } else {
        toggleBtn.textContent = '▲';
    }
    
    // 更新主内容区布局
    updateMainContentLayout();
}

// 更新主内容区布局
function updateMainContentLayout() {
    const dataSourceBar = document.querySelector('.data-source-bar');
    const mainContent = document.querySelector('.main-content');

    // 添加null检查
    if (!dataSourceBar || !mainContent) {
        console.warn('DOM元素未找到，无法更新布局');
        return;
    }
    
    if (dataSourceBar.classList.contains('collapsed')) {
        // 收缩状态：使用更小的行高
        mainContent.style.gridTemplateRows = '60px 1fr';
    } else {
        // 展开状态：使用自动行高
        mainContent.style.gridTemplateRows = 'auto 1fr';
    }
}

// 将显示坐标转换为实际视频坐标
function displayToActual(displayX, displayY) {
    if (videoNaturalWidth === 0 || videoNaturalHeight === 0) {
        return { x: displayX, y: displayY };
    }
    
    const rect = getVideoDisplayRect();
    
    // 将显示坐标转换为相对于视频显示区域的坐标
    const relativeX = displayX - rect.x;
    const relativeY = displayY - rect.y;
    
    // 转换为实际视频坐标
    const actualX = relativeX / rect.scaleX;
    const actualY = relativeY / rect.scaleY;
    
    // 确保坐标在有效范围内
    return {
        x: Math.max(0, Math.min(videoNaturalWidth, actualX)),
        y: Math.max(0, Math.min(videoNaturalHeight, actualY))
    };
}

// 绘图事件处理函数
function startDrawing(e) {
    // 仅处理鼠标左键（右键用于完成绘制）
    if (e && typeof e.button === 'number' && e.button !== 0) return;
    e && e.preventDefault();

    // 获取鼠标在画布上的坐标
    const rect = drawCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // 将显示坐标转换为实际坐标
    const actualPoint = displayToActual(x, y);

    // 点击式绘制：每次左键点击追加一个“固定点”，同时维持一个“预览点”（最后一个点随鼠标移动）
    // 若当前已有正在绘制的对象，则优先向该对象追加点，不受 currentTool 影响
    if (currentLane) {
        const lastIdx = currentLane.points.length - 1;
        currentLane.points[lastIdx] = actualPoint; // 固化预览点
        currentLane.points.push({ ...actualPoint }); // 追加新的预览点
        selectedItem = currentLane;
        redrawAll();
        updateUI();
        return;
    }
    if (currentTrigger) {
        const lastIdx = currentTrigger.points.length - 1;
        currentTrigger.points[lastIdx] = actualPoint; // 固化预览点
        currentTrigger.points.push({ ...actualPoint }); // 追加新的预览点
        selectedItem = currentTrigger;
        redrawAll();
        updateUI();
        return;
    }

    // 未在绘制：根据当前工具开始新绘制
    if (currentTool === 'lane') {
        // 开始绘制车道：第一个点 + 预览点（与第一个点重合，随后mousemove更新）
        const laneWidth = parseInt(document.getElementById('laneWidth')?.value || '3', 10);
        const laneColor = document.getElementById('laneColor')?.value || '#4285F4';

        currentLane = {
            id: Date.now(),
            type: 'lane',
            number: lanes.length + 1,
            name: `车道${lanes.length + 1}`,
            color: laneColor,
            width: Number.isFinite(laneWidth) ? laneWidth : 3,
            points: [actualPoint, { ...actualPoint }] // 最后一个点为预览点
        };
        lanes.push(currentLane);
        selectedItem = currentLane;
    } else if (currentTool === 'trigger') {
        const triggerWidth = parseInt(document.getElementById('triggerWidth')?.value || '2', 10);
        const triggerColor = document.getElementById('triggerColor')?.value || '#FF6D00';
        const triggerName = document.getElementById('triggerName')?.value || `触发线${triggers.length + 1}`;

        currentTrigger = {
            id: Date.now(),
            type: 'trigger',
            name: triggerName,
            color: triggerColor,
            width: Number.isFinite(triggerWidth) ? triggerWidth : 2,
            points: [actualPoint, { ...actualPoint }] // 最后一个点为预览点
        };
        triggers.push(currentTrigger);
        selectedItem = currentTrigger;
    }

    redrawAll();
    updateUI();
}

function draw(e) {
    e && e.preventDefault();

    if (!currentLane && !currentTrigger) return;

    // 获取鼠标在画布上的坐标
    const rect = drawCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // 将显示坐标转换为实际坐标
    const actualPoint = displayToActual(x, y);

    // 更新“预览点”（最后一个点）
    if (currentLane && currentLane.points.length >= 1) {
        currentLane.points[currentLane.points.length - 1] = actualPoint;
    } else if (currentTrigger && currentTrigger.points.length >= 1) {
        currentTrigger.points[currentTrigger.points.length - 1] = actualPoint;
    }

    redrawAll();
}


function stopDrawing(e) {
    // 兼容旧逻辑：现在采用点击式绘制，不再依赖 mouseup 停止
    e && e.preventDefault();
    redrawAll();
}

function completeDrawing(e) {
    // 右键（contextmenu）/双击完成绘制
    e && e.preventDefault();

    // 完成车道：移除预览点；不足2个点则丢弃
    if (currentLane) {
        if (currentLane.points.length >= 2) {
            currentLane.points.pop(); // 移除预览点
        }
        if (currentLane.points.length < 2) {
            const idx = lanes.findIndex(x => x && x.id === currentLane.id);
            if (idx >= 0) lanes.splice(idx, 1);
            if (selectedItem && selectedItem.id === currentLane.id) selectedItem = null;
        }
        currentLane = null;
    }

    // 完成触发线：移除预览点；不足2个点则丢弃
    if (currentTrigger) {
        if (currentTrigger.points.length >= 2) {
            currentTrigger.points.pop(); // 移除预览点
        }
        if (currentTrigger.points.length < 2) {
            const idx = triggers.findIndex(x => x && x.id === currentTrigger.id);
            if (idx >= 0) triggers.splice(idx, 1);
            if (selectedItem && selectedItem.id === currentTrigger.id) selectedItem = null;
        }
        currentTrigger = null;
    }

    redrawAll();
    updateUI();
}

function checkControlPointClick(e) {
    e.preventDefault();
    
    // 获取鼠标在画布上的坐标
    const rect = drawCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    // 检查是否点击了控制点
    const allItems = [...lanes, ...triggers];
    
    for (const item of allItems) {
        for (const point of item.points) {
            const displayPoint = actualToDisplay(point.x, point.y);
            const distance = Math.sqrt(Math.pow(x - displayPoint.x, 2) + Math.pow(y - displayPoint.y, 2));
            
            if (distance <= 10) { // 控制点半径
                selectedItem = item;
                redrawAll();
                updateUI();
                return true;
            }
        }
    }
    
    return false;
}

function checkLineClick(e) {
    e.preventDefault();
    
    // 获取鼠标在画布上的坐标
    const rect = drawCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    // 检查是否点击了线段
    const allItems = [...lanes, ...triggers];
    
    for (const item of allItems) {
        if (item.points.length < 2) continue;
        
        for (let i = 0; i < item.points.length - 1; i++) {
            const p1 = actualToDisplay(item.points[i].x, item.points[i].y);
            const p2 = actualToDisplay(item.points[i + 1].x, item.points[i + 1].y);
            
            // 计算点到线段的距离
            const distance = pointToLineDistance(x, y, p1.x, p1.y, p2.x, p2.y);
            
            if (distance <= 10) { // 线段点击阈值
                selectedItem = item;
                redrawAll();
                updateUI();
                return true;
            }
        }
    }
    
    return false;
}

// 计算点到线段的距离
function pointToLineDistance(px, py, x1, y1, x2, y2) {
    const A = px - x1;
    const B = py - y1;
    const C = x2 - x1;
    const D = y2 - y1;
    
    const dot = A * C + B * D;
    const lenSq = C * C + D * D;
    let param = -1;
    
    if (lenSq !== 0) {
        param = dot / lenSq;
    }
    
    let xx, yy;
    
    if (param < 0) {
        xx = x1;
        yy = y1;
    } else if (param > 1) {
        xx = x2;
        yy = y2;
    } else {
        xx = x1 + param * C;
        yy = y1 + param * D;
    }
    
    const dx = px - xx;
    const dy = py - yy;
    
    return Math.sqrt(dx * dx + dy * dy);
}

// 初始化画布事件监听器
function initializeCanvasEventListeners() {
    // 获取Canvas元素
    drawCanvas = document.getElementById('drawCanvas');
    overlayCanvas = document.getElementById('overlayCanvas');

    if (!drawCanvas || !overlayCanvas) {
        console.warn('Canvas元素未找到，无法绑定事件');
        return;
    }

    // 获取2D上下文
    ctx = drawCanvas.getContext('2d');
    overlayCtx = overlayCanvas.getContext('2d');

    // 防止重复绑定（initApp 可能被多次调用）
    if (drawCanvas.dataset && drawCanvas.dataset.eventsBound === '1') {
        return;
    }
    if (drawCanvas.dataset) drawCanvas.dataset.eventsBound = '1';

    // 鼠标移动：更新预览点
    drawCanvas.addEventListener('mousemove', draw);

    // 右键完成绘制（阻止系统右键菜单）
    drawCanvas.addEventListener('contextmenu', function(e) {
        e.preventDefault();
        // 仅在正在绘制时响应
        if (currentLane || currentTrigger) {
            completeDrawing(e);
        }
        return false;
    });

    // 左键点击：优先做选择；若在绘制中则追加点；否则开始新绘制
    drawCanvas.addEventListener('mousedown', function(e) {
        // 右键由 contextmenu 处理，这里直接忽略
        if (e && typeof e.button === 'number' && e.button === 2) return;

        // 如果正在绘制：任何左键点击都追加一个点
        if (currentLane || currentTrigger) {
            startDrawing(e);
            return;
        }

        // 未在绘制：先尝试选择控制点/线段，选择失败再开始新绘制
        if (!checkControlPointClick(e)) {
            if (!checkLineClick(e)) {
                startDrawing(e);
            }
        }
    });

    // 双击也允许完成（可选）
    drawCanvas.addEventListener('dblclick', function(e) {
        if (currentLane || currentTrigger) {
            completeDrawing(e);
        }
    });
}

// 在initApp函数中调用初始化
function initApp() {
    initializeCanvas();

    try {
        initializeEventListeners(); // 即使这里有问题，也不影响定时器启动
    } catch (e) {
        console.error('[initializeEventListeners] crashed:', e);
    }

    updateUI();

    // 开始定期更新统计数据
    startStatsUpdate();
    // 延迟检查后端健康状态
    setTimeout(checkBackendHealth, 1000);
    
    // 绑定顶部导航栏按钮事件
    document.getElementById('saveConfigBtn').addEventListener('click', saveConfig);
    document.getElementById('loadConfigBtn').addEventListener('click', loadConfig);
    document.getElementById('exportDataBtn').addEventListener('click', exportData);
    
    // 绑定数据源区域按钮事件
    document.querySelector('#onlineTab .primary-btn').addEventListener('click', connect);
    document.querySelector('#recordTab .primary-btn').addEventListener('click', loadRecord);
    
    // 绑定标签页切换按钮事件
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const tabName = this.textContent === '在线配置' ? 'online' : 'record';
            switchTab(tabName);
        });
    });
    
    // 绑定绘制工具按钮事件
    document.querySelectorAll('.tool-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            if (this.textContent.includes('车道')) {
                setTool('lane');
            } else if (this.textContent.includes('触发线')) {
                setTool('trigger');
            } else if (this.textContent.includes('清空')) {
                clearAll();
            }
        });
    });
    
    // 绑定全屏按钮事件
    document.querySelector('.video-controls .control-btn').addEventListener('click', toggleFullscreen);
    
    // 绑定面板标签页切换事件
    document.querySelectorAll('.panel-tab-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const tabName = this.textContent === '实时统计数据' ? 'stats' : 
                           this.textContent === '车道列表' ? 'lanes' : 'triggers';
            switchPanelTab(tabName);
        });
    });
    
    // 初始化画布事件监听器
    initializeCanvasEventListeners();
    
    // 默认设置为收缩状态
    const dataSourceBar = document.querySelector('.data-source-bar');
    const toggleBtn = document.getElementById('toggleDataSource');
    
    dataSourceBar.classList.add('collapsed');
    toggleBtn.classList.add('collapsed');
    toggleBtn.textContent = '▼';
    
    updateMainContentLayout();
    
    // 延迟执行以确保DOM完全加载
    setTimeout(() => {
        adjustVideoSize();
        
        // 监听标签页切换，确保视频尺寸正确
        const tabs = document.querySelectorAll('.tab-btn');
        tabs.forEach(tab => {
            tab.addEventListener('click', function() {
                setTimeout(adjustVideoSize, 100); // 延迟调整
            });
        });
    }, 300);
}

// 将实际视频坐标转换为显示坐标
function actualToDisplay(actualX, actualY) {
    if (videoNaturalWidth === 0 || videoNaturalHeight === 0) {
        return { x: actualX, y: actualY };
    }
    
    const rect = getVideoDisplayRect();
    
    // 将实际坐标转换为显示坐标
    const displayX = actualX * rect.scaleX + rect.x;
    const displayY = actualY * rect.scaleY + rect.y;
    
    return { x: displayX, y: displayY };
}


// 获取视频在容器中的实际显示区域（考虑object-fit: contain）
function getVideoDisplayRect() {
    const containerWidth = videoPlayer.offsetWidth;
    const containerHeight = videoPlayer.offsetHeight;
    
    if (videoNaturalWidth === 0 || videoNaturalHeight === 0) {
        return { x: 0, y: 0, width: containerWidth, height: containerHeight, scaleX: 1, scaleY: 1 };
    }
    
    const videoAspect = videoNaturalWidth / videoNaturalHeight;
    const containerAspect = containerWidth / containerHeight;
    
    let displayWidth, displayHeight, offsetX, offsetY;
    
    if (videoAspect > containerAspect) {
        // 视频更宽，以宽度为准
        displayWidth = containerWidth;
        displayHeight = containerWidth / videoAspect;
        offsetX = 0;
                offsetY = (containerHeight - displayHeight) / 2; 
            } else { 
        // 视频更高，以高度为准
            displayWidth = containerHeight * videoAspect; 
            displayHeight = containerHeight; 
        offsetX = (containerWidth - displayWidth) / 2;
        offsetY = 0;
    }
    
    const scaleX = displayWidth / videoNaturalWidth;
                const scaleY = displayHeight / videoNaturalHeight; 
    
    return {
        x: offsetX,
        y: offsetY,
        width: displayWidth,
        height: displayHeight,
        scaleX: scaleX,
        scaleY: scaleY
    };
}

async function confirmChannelSelect() { 
    const cameraChannel = document.getElementById('cameraChannel').value; 
    const eventChannel = document.getElementById('eventChannel').value; 
    const boxChannel = document.getElementById('boxChannel').value; 
    const pointsChannel = document.getElementById('pointsChannel').value; 
    if (currentRecordFile) { 
        const formData = new FormData(); 
        formData.append('record_file', currentRecordFile); 
        formData.append('camera_channel', cameraChannel); 
        formData.append('event_channel', eventChannel); 
        formData.append('box_channel', boxChannel); 
        formData.append('points_channel', pointsChannel); 
        try { 
            const response = await fetch(`${API_BASE_URL}/record/playRecord`, { method: 'POST', body: formData }); 
            const data = await response.json(); 
            if (data.success) { 
                isConnected = true; 
                startVideoStream(); 
                updateConnectionStatus(true); 
                closeChannelSelectModal(); 
                showNotification('记录文件加载成功！', 'success'); 
            } else { 
                throw new Error(data.message || '播放失败'); 
            } 
        } catch (error) { 
            console.error('播放错误:', error); 
            alert('播放失败: ' + error.message); 
        } 
    } 
}