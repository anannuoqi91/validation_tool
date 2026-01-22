// 全局变量
let currentTool = 'lane'; // 当前工具: 'lane', 'trigger', 'select'
let isDrawing = false;
let currentLane = null;
let currentTrigger = null;
let lanes = [];
let triggers = [];
let selectedItem = null;
let isDragging = false;
let dragStart = null;
let dragTarget = null;

// 视频相关变量
let videoPlayer = document.getElementById('videoPlayer');
let drawCanvas = document.getElementById('drawCanvas');
let overlayCanvas = document.getElementById('overlayCanvas');
let ctx = drawCanvas.getContext('2d');
let overlayCtx = overlayCanvas.getContext('2d');

// 视频实际尺寸（用于坐标转换）
let videoNaturalWidth = 0;
let videoNaturalHeight = 0;

// 初始化
window.addEventListener('load', () => {
    initializeCanvas();
    initializeEventListeners();
    updateUI();
    
    // 开始定期更新统计数据，每1秒更新一次
    startStatsUpdate();
});

// 定期更新统计数据
let statsUpdateInterval = null;

function startStatsUpdate() {
    // 清除现有的定时器（如果有）
    if (statsUpdateInterval) {
        clearInterval(statsUpdateInterval);
    }
    
    // 每1秒更新一次统计数据
    statsUpdateInterval = setInterval(updateStats, 1000);
}

// 更新统计数据
function updateStats() {
    fetch('/api/stats')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const statsContainer = document.getElementById('statsContainer');
                const stats = data.stats;
                
                // 清空容器
                statsContainer.innerHTML = '';
                
                if (Object.keys(stats).length === 0) {
                    // 没有统计数据
                    statsContainer.innerHTML = '<div class="stats-item"><span class="stats-label">等待数据...</span></div>';
                    return;
                }
                
                // 添加每个区域的统计数据
                Object.keys(stats).forEach(regionName => {
                    const regionStats = stats[regionName];
                    const statsItem = document.createElement('div');
                    statsItem.className = 'stats-item';
                    
                    // 处理总计数据的显示
                    const displayName = regionName === 'total' ? '总计' : regionName;
                    
                    statsItem.innerHTML = `
                        <span class="stats-label">${displayName}</span>
                        <div class="stats-count">${regionStats.image_count}</div>
                        <div class="stats-subcount">事件数: ${regionStats.event_count}</div>
                    `;
                    
                    // 为总计添加特殊样式
                    if (regionName === 'total') {
                        statsItem.style.borderTop = '2px solid #4285F4';
                        statsItem.style.fontWeight = 'bold';
                    }
                    
                    statsContainer.appendChild(statsItem);
                });
            }
        })
        .catch(error => {
            console.error('Error updating stats:', error);
        });
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

// 初始化事件监听器
function initializeEventListeners() {
    // 视频控制
    document.getElementById('fullscreenBtn').addEventListener('click', toggleFullscreen);
    
    // 数据源设置
    document.getElementById('onlineTab').addEventListener('click', () => switchTab('online'));
    document.getElementById('recordTab').addEventListener('click', () => switchTab('record'));
    document.getElementById('connectBtn').addEventListener('click', connectRTSP);
    document.getElementById('loadRecordBtn').addEventListener('click', loadRecordFile);
    
    // 绘制工具
    document.getElementById('laneBtn').addEventListener('click', () => setTool('lane'));
    document.getElementById('triggerBtn').addEventListener('click', () => setTool('trigger'));
    document.getElementById('clearBtn').addEventListener('click', clearAll);
    
    // 画布事件
    drawCanvas.addEventListener('mousedown', startDrawing);
    drawCanvas.addEventListener('mousemove', draw);
    drawCanvas.addEventListener('mouseup', stopDrawing);
    drawCanvas.addEventListener('mouseleave', stopDrawing);
    drawCanvas.addEventListener('dblclick', completeDrawing);
    
    // 数据管理
    document.getElementById('saveBtn').addEventListener('click', saveConfig);
    document.getElementById('loadBtn').addEventListener('click', loadConfig);
    document.getElementById('exportBtn').addEventListener('click', exportData);
    
    // 属性设置
    document.getElementById('laneNumber').addEventListener('input', updateLaneProperties);
    document.getElementById('laneName').addEventListener('input', updateLaneProperties);
    document.getElementById('laneColor').addEventListener('input', updateLaneProperties);
    document.getElementById('laneWidth').addEventListener('input', updateLaneProperties);
    document.getElementById('triggerName').addEventListener('input', updateTriggerProperties);
    document.getElementById('triggerColor').addEventListener('input', updateTriggerProperties);
    document.getElementById('triggerWidth').addEventListener('input', updateTriggerProperties);
    
    // 删除按钮事件已移至列表项中
}

// 切换视频源标签
function switchTab(tabName) {
    // 更新标签按钮
    document.getElementById('onlineTab').classList.remove('active');
    document.getElementById('recordTab').classList.remove('active');
    document.getElementById(tabName + 'Tab').classList.add('active');
    
    // 更新内容面板
    document.getElementById('onlinePanel').classList.remove('active');
    document.getElementById('recordPanel').classList.remove('active');
    document.getElementById(tabName + 'Panel').classList.add('active');
}

// 连接RTSP流
function connectRTSP() {
    const rtspUrl = document.getElementById('rtspUrl').value;
    const cyberEventChannel = document.getElementById('cyberEventChannel').value;
    const cyberPointcloudChannel = document.getElementById('cyberPointcloudChannel').value;
    
    if (!rtspUrl || !cyberEventChannel) {
        alert('请输入RTSP URL和Cyber Event Channel');
        return;
    }
    
    // 这里需要与后端通信，获取视频流
    fetch('/api/rtsp/connect', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
            rtsp_url: rtspUrl,
            cyber_event_channel: cyberEventChannel,
            cyber_pointcloud_channel: cyberPointcloudChannel
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // 连接成功后，设置视频源
            videoPlayer.src = data.stream_url;
            // 等待图片加载完成后获取实际尺寸
            videoPlayer.onload = function() {
                if (videoPlayer.naturalWidth > 0 && videoPlayer.naturalHeight > 0) {
                    videoNaturalWidth = videoPlayer.naturalWidth;
                    videoNaturalHeight = videoPlayer.naturalHeight;
                    resizeCanvas();
                }
            };
        } else {
            alert('连接失败: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('连接失败: ' + error.message);
    });
}

// 加载Record文件
function loadRecordFile() {
    const fileInput = document.getElementById('recordFile');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('请选择一个Record文件');
        return;
    }
    
    const formData = new FormData();
    formData.append('record_file', file);
    
    // 上传文件并获取视频流
    fetch('/api/record/load', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // 设置视频源
            videoPlayer.src = data.stream_url;
            // 等待图片加载完成后获取实际尺寸
            videoPlayer.onload = function() {
                if (videoPlayer.naturalWidth > 0 && videoPlayer.naturalHeight > 0) {
                    videoNaturalWidth = videoPlayer.naturalWidth;
                    videoNaturalHeight = videoPlayer.naturalHeight;
                    resizeCanvas();
                }
            };
        } else {
            alert('加载失败: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('加载失败: ' + error.message);
    });
}

// 设置绘制工具
function setTool(tool) {
    currentTool = tool;
    
    // 重置当前绘制对象
    currentLane = null;
    currentTrigger = null;
    
    // 更新工具按钮状态
    document.querySelectorAll('.tool-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(tool + 'Btn').classList.add('active');
    
    // 更新属性面板：无论是否有选中项，都显示当前工具的属性面板
    document.getElementById('laneProperties').style.display = tool === 'lane' ? 'block' : 'none';
    document.getElementById('triggerProperties').style.display = tool === 'trigger' ? 'block' : 'none';
    
    // 清除选中状态
    selectedItem = null;
    updateUI();
}

// 开始绘制 - 鼠标单击时添加点
function startDrawing(e) {
    const rect = drawCanvas.getBoundingClientRect();
    const displayX = e.clientX - rect.left;
    const displayY = e.clientY - rect.top;
    
    // 检查是否正在绘制中
    const isDrawingLane = currentTool === 'lane' && currentLane !== null;
    const isDrawingTrigger = currentTool === 'trigger' && currentTrigger !== null;
    const isDrawing = isDrawingLane || isDrawingTrigger;
    
    // 如果正在绘制中，允许在任何位置添加点（包括已有线条上）
    if (isDrawing) {
        // 将显示坐标转换为实际坐标
        const actualCoord = displayToActual(displayX, displayY);
        
        if (isDrawingLane) {
            // 在当前车道添加新点（允许重复）
            currentLane.points.push({ x: actualCoord.x, y: actualCoord.y });
        } else if (isDrawingTrigger) {
            // 在当前触发线添加新点（允许重复）
            currentTrigger.points.push({ x: actualCoord.x, y: actualCoord.y });
        }
        
        // 更新UI和重绘
        updateUI();
        redrawAll();
        return;
    }
    
    // 如果没有正在绘制，检查是否点击了控制点（用于拖动）
    const clickedPoint = checkControlPointClick(displayX, displayY);
    if (clickedPoint) {
        isDragging = true;
        dragStart = { x: displayX, y: displayY };
        dragTarget = clickedPoint;
        selectedItem = clickedPoint.item;
        updateUI();
        return;
    }
    
    // 检查是否点击了线条（用于选择）
    const clickedItem = checkLineClick(displayX, displayY);
    if (clickedItem) {
        selectedItem = clickedItem;
        updateUI();
        return;
    }
    
    // 取消选择，开始新的绘制
    selectedItem = null;
    updateUI();
    
    // 将显示坐标转换为实际坐标
    const actualCoord = displayToActual(displayX, displayY);
    
    // 单击添加点（开始新的绘制）
    if (currentTool === 'lane') {
        // 开始新的车道绘制
        const laneNumber = parseInt(document.getElementById('laneNumber').value);
        const laneName = document.getElementById('laneName').value || `车道${laneNumber}`;
        currentLane = {
            id: Date.now(),
            number: laneNumber,
            name: laneName,
            points: [{ x: actualCoord.x, y: actualCoord.y }],
            color: document.getElementById('laneColor').value,
            width: parseInt(document.getElementById('laneWidth').value),
            type: 'lane'
        };
        lanes.push(currentLane);
        currentTrigger = null;
    } else if (currentTool === 'trigger') {
        // 开始新的触发线绘制
        currentTrigger = {
            id: Date.now(),
            name: document.getElementById('triggerName').value || '触发线',
            points: [{ x: actualCoord.x, y: actualCoord.y }],
            color: '#0000ff', // 触发线默认为蓝色
            width: parseInt(document.getElementById('triggerWidth').value),
            type: 'trigger'
        };
        triggers.push(currentTrigger);
        currentLane = null;
    }
    
    // 更新UI和重绘
    updateUI();
    redrawAll();
}

// 绘制过程 - 鼠标移动时只显示预览线
function draw(e) {
    // 拖动控制点时的处理
    if (isDragging && dragTarget) {
        const rect = drawCanvas.getBoundingClientRect();
        const displayX = e.clientX - rect.left;
        const displayY = e.clientY - rect.top;
        
        // 将显示坐标转换为实际坐标并更新
        const actualCoord = displayToActual(displayX, displayY);
        dragTarget.point.x = actualCoord.x;
        dragTarget.point.y = actualCoord.y;
        
        redrawAll();
        return;
    }
    
    // 鼠标移动时不添加点，只绘制预览线
    if ((currentTool === 'lane' && currentLane && currentLane.points.length > 0) || 
        (currentTool === 'trigger' && currentTrigger && currentTrigger.points.length > 0)) {
        redrawAll();
        
        const rect = drawCanvas.getBoundingClientRect();
        const displayX = e.clientX - rect.left;
        const displayY = e.clientY - rect.top;
        
        ctx.strokeStyle = '#FF0000'; // 预览线为红色
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 5]); // 虚线
        
        // 获取当前绘制对象的最后一个点（实际坐标）
        const lastPoint = currentTool === 'lane' 
            ? currentLane.points[currentLane.points.length - 1]
            : currentTrigger.points[currentTrigger.points.length - 1];
        
        // 将实际坐标转换为显示坐标
        const lastDisplayPoint = actualToDisplay(lastPoint.x, lastPoint.y);
        
        // 绘制预览线
        ctx.beginPath();
        ctx.moveTo(lastDisplayPoint.x, lastDisplayPoint.y);
        ctx.lineTo(displayX, displayY);
        ctx.stroke();
        ctx.setLineDash([]); // 重置为实线
    }
}

// 停止绘制 - 拖动控制点时停止拖动
function stopDrawing() {
    isDragging = false;
    dragTarget = null;
    redrawAll();
}

// 去除末尾重复点（双击同一点时防止重复）
function removeDuplicateTail(points, threshold = 0.5) {
    if (!points || points.length < 2) return;
    const last = points[points.length - 1];
    const prev = points[points.length - 2];
    if (Math.abs(last.x - prev.x) <= threshold && Math.abs(last.y - prev.y) <= threshold) {
        points.pop();
    }
}

// 完成绘制（双击）
function completeDrawing(e) {
    // 完成当前绘制的对象
    if (currentTool === 'lane' && currentLane) {
        removeDuplicateTail(currentLane.points);
        // 对于车道，自动闭合多边形
        if (currentLane.points.length >= 3) {
            // 自动闭合多边形（连接最后一个点和第一个点）
            // 注意：不需要实际添加点，在绘制时自动闭合即可
            currentLane = null;
        }
    } else if (currentTool === 'trigger' && currentTrigger) {
        removeDuplicateTail(currentTrigger.points);
        // 对于触发线，只需要两个点
        if (currentTrigger.points.length >= 2) {
            // 已经有足够的点，完成绘制
            currentTrigger = null;
        }
    }
    
    updateUI();
    redrawAll();
}

// 选择功能已集成到startDrawing函数中

// 检查是否点击了控制点
function checkControlPointClick(displayX, displayY) {
    const allItems = [...lanes, ...triggers];
    
    for (const item of allItems) {
        for (const point of item.points) {
            // 将实际坐标转换为显示坐标
            const displayPoint = actualToDisplay(point.x, point.y);
            const distance = Math.sqrt(Math.pow(displayX - displayPoint.x, 2) + Math.pow(displayY - displayPoint.y, 2));
            if (distance < 8) { // 控制点半径
                return { item, point };
            }
        }
    }
    
    return null;
}

// 检查是否点击了线条
function checkLineClick(displayX, displayY) {
    const allItems = [...lanes, ...triggers];
    
    for (const item of allItems) {
        if (item.points.length < 2) continue;
        
        for (let i = 0; i < item.points.length - 1; i++) {
            // 将实际坐标转换为显示坐标
            const p1Display = actualToDisplay(item.points[i].x, item.points[i].y);
            const p2Display = actualToDisplay(item.points[i + 1].x, item.points[i + 1].y);
            
            // 计算点到线段的距离
            const distance = pointToLineDistance(displayX, displayY, p1Display.x, p1Display.y, p2Display.x, p2Display.y);
            if (distance < item.width + 5) { // 线条宽度 + 容差
                return item;
            }
        }
    }
    
    return null;
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

// 获取线段中点
function getMidPoint(p1, p2) {
    return {
        x: (p1.x + p2.x) / 2,
        y: (p2.y + p2.y) / 2
    };
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

// 更新UI
function updateUI() {
    // 更新车道列表
    updateLanesList();
    
    // 更新触发线列表
    updateTriggersList();
    
    // 更新属性面板
    updatePropertiesPanel();
}

// 更新车道列表
function updateLanesList() {
    const lanesList = document.getElementById('lanesList');
    lanesList.innerHTML = '';
    
    lanes.forEach(lane => {
        const laneCard = document.createElement('div');
        laneCard.className = 'item-card' + (selectedItem === lane ? ' selected' : '');
        laneCard.innerHTML = `
            <div class="item-info">
                <div class="item-title">${lane.name || `车道 ${lane.number}`}</div>
                <div class="item-details">编号: ${lane.number} · ${lane.points.length} 个点</div>
            </div>
            <button class="delete-btn" title="删除车道">🗑️</button>
        `;
        
        // 点击卡片选择车道
        laneCard.querySelector('.item-info').addEventListener('click', () => {
            selectedItem = lane;
            // 更新属性面板显示
            document.getElementById('laneProperties').style.display = 'block';
            document.getElementById('triggerProperties').style.display = 'none';
            updateUI();
            redrawAll();
        });
        
        // 点击删除按钮删除车道
        laneCard.querySelector('.delete-btn').addEventListener('click', (e) => {
            e.stopPropagation(); // 防止触发卡片点击事件
            deleteLane(lane.id);
        });
        
        lanesList.appendChild(laneCard);
    });
}

// 更新触发线列表
function updateTriggersList() {
    const triggersList = document.getElementById('triggersList');
    triggersList.innerHTML = '';
    
    triggers.forEach(trigger => {
        const triggerCard = document.createElement('div');
        triggerCard.className = 'item-card' + (selectedItem === trigger ? ' selected' : '');
        triggerCard.innerHTML = `
            <div class="item-info">
                <div class="item-title">${trigger.name}</div>
                <div class="item-details">${trigger.points.length} 个点</div>
            </div>
            <button class="delete-btn" title="删除触发线">🗑️</button>
        `;
        
        // 点击卡片选择触发线
        triggerCard.querySelector('.item-info').addEventListener('click', () => {
            selectedItem = trigger;
            // 更新属性面板显示
            document.getElementById('laneProperties').style.display = 'none';
            document.getElementById('triggerProperties').style.display = 'block';
            updateUI();
            redrawAll();
        });
        
        // 点击删除按钮删除触发线
        triggerCard.querySelector('.delete-btn').addEventListener('click', (e) => {
            e.stopPropagation(); // 防止触发卡片点击事件
            deleteTrigger(trigger.id);
        });
        
        triggersList.appendChild(triggerCard);
    });
}

// 更新属性面板
function updatePropertiesPanel() {
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

// 切换全屏
function toggleFullscreen() {
    const videoContainer = document.querySelector('.video-container');
    
    if (!document.fullscreenElement) {
        videoContainer.requestFullscreen().catch(err => {
            console.error(`Error attempting to enable fullscreen: ${err.message}`);
        });
    } else {
        document.exitFullscreen();
    }
}

// 删除特定ID的车道
function deleteLane(laneId) {
    // 确认删除
    if (!confirm('确定要删除这条车道吗？')) {
        return;
    }
    
    try {
        // 从车道列表中删除
        const index = lanes.findIndex(lane => lane.id === laneId);
        if (index !== -1) {
            lanes.splice(index, 1);
        }
        
        // 如果删除的是当前选中的车道，清除选中状态
        if (selectedItem && selectedItem.type === 'lane' && selectedItem.id === laneId) {
            selectedItem = null;
        }
        
        // 重新绘制
        redrawAll();
        updateUI();
        
        console.log('成功删除车道');
    } catch (error) {
        console.error('删除车道失败:', error);
        alert('删除车道失败，请重试');
    }
}

// 删除特定ID的触发线
function deleteTrigger(triggerId) {
    // 确认删除
    if (!confirm('确定要删除这条触发线吗？')) {
        return;
    }
    
    try {
        // 从触发线列表中删除
        const index = triggers.findIndex(trigger => trigger.id === triggerId);
        if (index !== -1) {
            triggers.splice(index, 1);
        }
        
        // 如果删除的是当前选中的触发线，清除选中状态
        if (selectedItem && selectedItem.type === 'trigger' && selectedItem.id === triggerId) {
            selectedItem = null;
        }
        
        // 重新绘制
        redrawAll();
        updateUI();
        
        console.log('成功删除触发线');
    } catch (error) {
        console.error('删除触发线失败:', error);
        alert('删除触发线失败，请重试');
    }
}

// 保存配置
function saveConfig() {
    const config = {
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
        }
    };
    
    fetch('/api/config/save', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(config)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('配置保存成功');
        } else {
            alert('保存失败: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('保存失败: ' + error.message);
    });
}

// 加载配置
function loadConfig() {
    fetch('/api/config/load')
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const config = data.config;
            lanes = (config.lanes || []).map((lane, idx) => ({
                ...lane,
                name: lane.name || `车道${lane.number || idx + 1}`
            }));
            triggers = config.triggers || [];
            
            // 如果配置中有视频尺寸信息，且当前视频尺寸为0，尝试使用配置中的尺寸
            // 但通常应该等待视频加载完成后再加载配置
            if (config.videoSize && videoNaturalWidth === 0 && videoNaturalHeight === 0) {
                videoNaturalWidth = config.videoSize.width;
                videoNaturalHeight = config.videoSize.height;
            }
            
            // 如果加载的坐标是显示坐标（旧格式），需要转换为实际坐标
            // 这里假设新格式已经使用实际坐标，旧格式需要转换
            // 但更好的方式是检查是否有videoSize字段
            
            selectedItem = null;
            redrawAll();
            updateUI();
            alert('配置加载成功');
        } else {
            alert('加载失败: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('加载失败: ' + error.message);
    });
}

// 导出数据
function exportData() {
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

// 清空所有内容
function clearAll() {
    if (confirm('确定要清空所有绘制内容吗？')) {
        lanes = [];
        triggers = [];
        selectedItem = null;
        currentLane = null;
        currentTrigger = null;
        redrawAll();
        updateUI();
    }
}