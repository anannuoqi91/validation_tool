// pointcloud.js
// ===============================
// 负责三维点云区域的 Three.js 初始化 & /points 数据流解析
// ===============================

// --- 一些常量配置 --- //

// 每个点的字节布局（和你 Python dtype 完全对应）
const POINT_STRIDE = 24; // x(4) + y(4) + z(4) + intensity(2) + pad(2) + timestamp(8)

// 后端 multipart boundary，需和后端 yield 的 "--frame\r\n" 对齐
// 如果你后端改成 "--pointcloud\r\n"，这里也要同步改
const POINTCLOUD_BOUNDARY = '--frame\r\n';

// --- Three.js 相关全局变量 --- //

let pcScene = null;
let pcCamera = null;
let pcRenderer = null;
let pcPoints = null;          // THREE.Points 对象
let pcAutoRotate = false;

let pcAnimationId = null;

let pcStreamStarted = false;

// --- 工具函数：字节数组处理 --- //

// 连接两个 Uint8Array
function concatUint8(a, b) {
    const c = new Uint8Array(a.length + b.length);
    c.set(a, 0);
    c.set(b, a.length);
    return c;
}

// 在 Uint8Array 中查找子数组
function indexOfSubarray(haystack, needle, fromIndex = 0) {
    outer: for (let i = fromIndex; i <= haystack.length - needle.length; i++) {
        for (let j = 0; j < needle.length; j++) {
            if (haystack[i + j] !== needle[j]) {
                continue outer;
            }
        }
        return i;
    }
    return -1;
}

// --- 解析单帧 point_core_bytes 为 Three.js 可用数据 --- //

function parsePointCoreToBuffers(u8) {
    // u8 可能是 Uint8Array，也可能是 ArrayBuffer
    let dv;
    if (u8 instanceof Uint8Array) {
        dv = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
    } else {
        dv = new DataView(u8);
    }

    const byteLength = dv.byteLength;
    const count = Math.floor(byteLength / POINT_STRIDE);

    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);

    let offset = 0;
    for (let i = 0; i < count; i++) {
        const x = dv.getFloat32(offset, true); offset += 4;
        const y = dv.getFloat32(offset, true); offset += 4;
        const z = dv.getFloat32(offset, true); offset += 4;

        const intensity = dv.getUint16(offset, true); offset += 2;
        offset += 2; // 跳过 padding

        // 跳过 timestamp(8字节)
        offset += 8;

        const base = i * 3;
        // positions[base] = x;
        // positions[base + 1] = y;
        // positions[base + 2] = z;
        const scale = 0.001; // mm -> m; 如果原来就是米，就设成 1
        positions[base]     = x * scale;
        positions[base + 1] = y * scale;
        positions[base + 2] = z * scale;

        // 用 intensity 简单映射成灰度颜色（0~1）
        // const g = Math.min(intensity / 65535, 1.0);
        // colors[base] = g;
        // colors[base + 1] = g;
        // colors[base + 2] = g;
        colors[base] = 1.0;
        colors[base + 1] = 1.0;
        colors[base + 2] = 1.0;
    }

    return { positions, colors, count };
}

// --- 用新一帧数据“全量更新”点云 --- //

function updatePointCloudFromFrame(u8) {
    const dv = u8 instanceof Uint8Array
        ? new DataView(u8.buffer, u8.byteOffset, u8.byteLength)
        : new DataView(u8);

    const byteLength = dv.byteLength;
    const count1 = Math.floor(byteLength / POINT_STRIDE);
    console.log('[pointcloud] frame bytes =', byteLength, 'points =', count1);

    if (count1 === 0) {
        console.warn('[pointcloud] 这一帧没有解析出点，请确认后端发的是纯 point_core_bytes');
        return;
    }
    const { positions, colors, count } = parsePointCoreToBuffers(u8);

    if (!pcPoints) {
        // 第一次：创建 geometry + material + points
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
        geometry.computeBoundingSphere();

        const material = new THREE.PointsMaterial({
            size: 0.1,          // 点大小，可按实际比例调
            vertexColors: true, // 使用每点颜色
            sizeAttenuation: true
        });

        pcPoints = new THREE.Points(geometry, material);
        pcScene.add(pcPoints);
    } else {
        // 后续帧：直接替换 attribute，实现“全量清空 + 更新”
        const geometry = pcPoints.geometry;

        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
        geometry.setDrawRange(0, positions.length / 3);
        geometry.computeBoundingSphere();

        geometry.attributes.position.needsUpdate = true;
        geometry.attributes.color.needsUpdate = true;
    }
}

// --- 解析 /points 的 multipart/x-mixed-replace 流 --- //

async function startPointCloudStream() {
    pcStreamStarted = true;
    const origin = window.BACKEND_ORIGIN || '';   // 来自 app.js
    const url = `${origin}/points`;
    console.log('[pointcloud] connecting to', url);

    let response;
    try {
        response = await fetch(url);
    } catch (err) {
        alert('fetch /points error: ' + err);
        console.error('[pointcloud] fetch /points error:', err);
        return;
    }

    if (!response.ok || !response.body) {
        console.error('[pointcloud] invalid response for /points', response.status);
        return;
    }

    const reader = response.body.getReader();

    const enc = new TextEncoder();
    const boundaryBytes = enc.encode(POINTCLOUD_BOUNDARY); // 例如 "--frame\r\n"
    const headerSepBytes = enc.encode('\r\n\r\n');

    let buffer = new Uint8Array(0);
    let firstBoundaryFound = false;

    while (true) {
        const { value, done } = await reader.read();
        if (done) {
            console.log('[pointcloud] stream ended');
            break;
        }
        if (!value) continue;

        // 追加新数据
        buffer = concatUint8(buffer, value);

        // 先找到第一个 boundary，把之前的丢掉
        if (!firstBoundaryFound) {
            const idx = indexOfSubarray(buffer, boundaryBytes, 0);
            if (idx === -1) {
                // 还没收到完整的第一个 boundary，继续读
                continue;
            }
            firstBoundaryFound = true;
            // 确保 buffer 从 boundary 开始
            buffer = buffer.slice(idx);
        }

        // 只要 buffer 里有两个 boundary，就说明中间是一帧完整数据
        while (true) {
            // 期望第一个 boundary 在开头
            let firstIdx = indexOfSubarray(buffer, boundaryBytes, 0);
            if (firstIdx === -1) {
                // 当前缓存中已经没有完整 boundary，等待更多数据
                break;
            }

            if (firstIdx !== 0) {
                // 意外情况：boundary 不在开头，把前面的丢掉
                buffer = buffer.slice(firstIdx);
                firstIdx = 0;
            }

            const secondIdx = indexOfSubarray(buffer, boundaryBytes, boundaryBytes.length);
            if (secondIdx === -1) {
                // 还没有第二个 boundary，说明这一帧还不完整
                break;
            }

            // framePart = [第一个 boundary 之后, 第二个 boundary 之前]
            const framePart = buffer.slice(boundaryBytes.length, secondIdx);

            // 更新 buffer，保留从第二个 boundary 开始的内容（给下一轮解析）
            buffer = buffer.slice(secondIdx);

            if (framePart.length === 0) continue;

            // framePart 结构：
            // Content-Type: ...\r\n\r\n<point_core_bytes>\r\n
            const headerSepIdx = indexOfSubarray(framePart, headerSepBytes, 0);
            if (headerSepIdx === -1) {
                // 理论上不会发生（一个 frame 一定完整），防御性处理
                continue;
            }

            const bodyWithEnd = framePart.slice(headerSepIdx + headerSepBytes.length);
            // 去掉结尾的 \r\n
            let body = bodyWithEnd;
            if (body.length >= 2 &&
                body[body.length - 2] === 13 &&
                body[body.length - 1] === 10) {
                body = body.slice(0, -2);
            }

            if (body.length > 0) {
                // 一帧 point_core_bytes 到手
                updatePointCloudFromFrame(body);
            }
        }
    }
}

// --- Three.js 初始化 & 动画循环 --- //

function initPointCloudViewer() {
    const container = document.getElementById('pointcloudContainer');
    if (!container) {
        console.error('[pointcloud] container #pointcloudContainer not found');
        return;
    }

    const width = container.clientWidth || 600;
    const height = container.clientHeight || 400;

    pcScene = new THREE.Scene();
    pcScene.background = new THREE.Color(0x000000);

    pcCamera = new THREE.PerspectiveCamera(60, width / height, 0.1, 5000);
    pcCamera.position.set(0, 0, 50);

    pcRenderer = new THREE.WebGLRenderer({ antialias: true });
    pcRenderer.setSize(width, height);
    pcRenderer.setPixelRatio(window.devicePixelRatio || 1);
    container.appendChild(pcRenderer.domElement);

    // 加一点坐标轴 / 网格帮助视觉
    const axes = new THREE.AxesHelper(10);
    pcScene.add(axes);

    const grid = new THREE.GridHelper(100, 20);
    grid.rotation.x = Math.PI / 2;
    pcScene.add(grid);

    // 只初始化 & 开始渲染循环，不自动连 /points
    animatePointCloud();
}

function animatePointCloud() {
    pcAnimationId = requestAnimationFrame(animatePointCloud);

    if (pcAutoRotate && pcScene) {
        pcScene.rotation.y += 0.003;
    }

    if (pcRenderer && pcCamera && pcScene) {
        pcRenderer.render(pcScene, pcCamera);
    }
}

// --- 对接 index.html 的按钮 --- //

// 重置视角
window.resetCamera = function () {
    if (!pcCamera || !pcScene) return;
    pcScene.rotation.set(0, 0, 0);
    pcCamera.position.set(0, 0, 50);
    pcCamera.lookAt(0, 0, 0);
};

// 自动旋转开关
window.toggleAutoRotate = function () {
    pcAutoRotate = !pcAutoRotate;
    const btn = document.getElementById('autoRotateBtn');
    if (btn) {
        btn.textContent = pcAutoRotate ? '停止旋转' : '自动旋转';
    }
};

// 加载示例点云（没有后端 /points 时可用）
window.loadSamplePointCloud = function () {
    const count = 5000;
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);

    for (let i = 0; i < count; i++) {
        const base = i * 3;
        positions[base] = (Math.random() - 0.5) * 50;
        positions[base + 1] = (Math.random() - 0.5) * 50;
        positions[base + 2] = (Math.random() - 0.5) * 50;

        colors[base] = Math.random();
        colors[base + 1] = Math.random();
        colors[base + 2] = Math.random();
    }

    updatePointCloudFromFrame(positions.buffer); // 利用同一个更新逻辑，这里偷懒直接传 buffer
};

// 提供给 app.js 的自适应尺寸函数
window.onWindowResize = function () {
    if (!pcRenderer || !pcCamera) return;

    const container = document.getElementById('pointcloudContainer');
    if (!container) return;

    const width = container.clientWidth || 600;
    const height = container.clientHeight || 400;

    pcCamera.aspect = width / height;
    pcCamera.updateProjectionMatrix();

    pcRenderer.setSize(width, height);
};

window.startPointCloudStreamSafe = function () {
    if (pcStreamStarted) {
        console.log('[pointcloud] stream already started, skip');
        return;
    }
    pcStreamStarted = true;

    // 真正启动异步流
    startPointCloudStream().catch(err => {
        console.error('[pointcloud] startPointCloudStream error:', err);
        // 失败的话允许重新尝试
        pcStreamStarted = false;
    });
};

// 页面加载完成后初始化
window.addEventListener('load', () => {
    initPointCloudViewer();
});