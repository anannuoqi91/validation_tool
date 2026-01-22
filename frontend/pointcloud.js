// 点云可视化逻辑
let scene, camera, renderer, pointCloud;
let autoRotate = false;
let animationId;

// 初始化Three.js场景
function initPointCloud() {
    const container = document.getElementById('pointcloudContainer');
    
    // 创建场景
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a1a);
    
    // 创建相机
    camera = new THREE.PerspectiveCamera(75, container.clientWidth / container.clientHeight, 0.1, 1000);
    camera.position.z = 5;
    
    // 创建渲染器
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(renderer.domElement);
    
    // 添加光源
    const ambientLight = new THREE.AmbientLight(0x404040);
    scene.add(ambientLight);
    
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.5);
    directionalLight.position.set(1, 1, 1);
    scene.add(directionalLight);
    
    // 添加坐标轴辅助
    const axesHelper = new THREE.AxesHelper(2);
    scene.add(axesHelper);
    
    // 窗口大小变化时调整渲染器
    window.addEventListener('resize', onWindowResize);
    
    // 开始动画循环
    animate();
}

// 窗口大小变化处理
function onWindowResize() {
    const container = document.getElementById('pointcloudContainer');
    if (container && container.clientWidth > 0 && container.clientHeight > 0) {
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    }
}

// 页面加载完成后初始化点云可视化
document.addEventListener('DOMContentLoaded', function() {
    // 等待DOM完全加载后初始化
    setTimeout(() => {
        initPointCloud();
        loadSamplePointCloud(); // 默认加载示例点云
        
        // 添加resize监听，确保布局变化时重新调整
        window.addEventListener('resize', onWindowResize);
    }, 100);
});

// 动画循环
function animate() {
    animationId = requestAnimationFrame(animate);
    
    if (autoRotate && pointCloud) {
        pointCloud.rotation.y += 0.01;
    }
    
    renderer.render(scene, camera);
}

// 重置相机视角
function resetCamera() {
    camera.position.set(0, 0, 5);
    camera.lookAt(0, 0, 0);
    
    if (pointCloud) {
        pointCloud.rotation.set(0, 0, 0);
    }
}

// 切换自动旋转
function toggleAutoRotate() {
    autoRotate = !autoRotate;
    const btn = document.getElementById('autoRotateBtn');
    btn.textContent = autoRotate ? '停止旋转' : '自动旋转';
    btn.style.background = autoRotate ? '#4CAF50' : '#4285F4';
}

// 加载示例点云数据
function loadSamplePointCloud() {
    // 创建示例点云数据（1000个随机点）
    const points = [];
    const colors = [];
    
    for (let i = 0; i < 1000; i++) {
        // 随机位置
        const x = (Math.random() - 0.5) * 4;
        const y = (Math.random() - 0.5) * 4;
        const z = (Math.random() - 0.5) * 4;
        points.push(x, y, z);
        
        // 根据位置设置颜色
        const r = (x + 2) / 4;
        const g = (y + 2) / 4;
        const b = (z + 2) / 4;
        colors.push(r, g, b);
    }
    
    // 创建点云几何体
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    
    // 创建点云材质
    const material = new THREE.PointsMaterial({
        size: 0.05,
        vertexColors: true,
        transparent: true,
        opacity: 0.8
    });
    
    // 移除现有的点云
    if (pointCloud) {
        scene.remove(pointCloud);
    }
    
    // 创建新的点云
    pointCloud = new THREE.Points(geometry, material);
    scene.add(pointCloud);
    
    console.log('示例点云加载完成');
}

// 从后端加载真实点云数据
async function loadRealPointCloud() {
    try {
        // 这里可以实现从后端API加载真实点云数据的逻辑
        console.log('加载真实点云数据...');
    } catch (error) {
        console.error('加载点云数据错误:', error);
    }
}