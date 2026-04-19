const canvas = document.getElementById("scene-canvas");

if (canvas && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  import("https://unpkg.com/three@0.165.0/build/three.module.js")
    .then((THREE) => {
      const renderer = new THREE.WebGLRenderer({
        canvas,
        alpha: true,
        antialias: true,
      });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
      renderer.setSize(window.innerWidth, window.innerHeight);

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(46, window.innerWidth / window.innerHeight, 0.1, 100);
      camera.position.set(0, 0, 8.2);

      const ambientLight = new THREE.AmbientLight(0xa9dff2, 1.2);
      scene.add(ambientLight);

      const pointLight = new THREE.PointLight(0x8ff6e5, 2.1, 50);
      pointLight.position.set(4, 5, 6);
      scene.add(pointLight);

      const warmLight = new THREE.PointLight(0xff9966, 1.35, 40);
      warmLight.position.set(-5, -3, 5);
      scene.add(warmLight);

      const mode = document.body.dataset.sceneMode || "marketing";
      const rootGroup = new THREE.Group();
      scene.add(rootGroup);

      const glassSphere = new THREE.Mesh(
        new THREE.IcosahedronGeometry(mode === "workspace" ? 1.7 : 2.2, 1),
        new THREE.MeshPhysicalMaterial({
          color: 0x83fff0,
          roughness: 0.18,
          transmission: 0.82,
          thickness: 1.2,
          transparent: true,
          opacity: 0.62,
          metalness: 0.05,
          clearcoat: 1,
          clearcoatRoughness: 0.12,
        }),
      );
      glassSphere.position.set(mode === "workspace" ? 2.7 : 2.2, mode === "workspace" ? -0.5 : 0.1, 0);
      rootGroup.add(glassSphere);

      const wireOrb = new THREE.Mesh(
        new THREE.IcosahedronGeometry(mode === "workspace" ? 2.15 : 2.6, 1),
        new THREE.MeshBasicMaterial({
          color: 0x89a9ff,
          wireframe: true,
          transparent: true,
          opacity: 0.28,
        }),
      );
      wireOrb.position.copy(glassSphere.position);
      wireOrb.scale.setScalar(1.18);
      rootGroup.add(wireOrb);

      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(mode === "workspace" ? 2.4 : 2.9, 0.04, 18, 120),
        new THREE.MeshBasicMaterial({
          color: 0x46d8c7,
          transparent: true,
          opacity: 0.4,
        }),
      );
      ring.rotation.x = 1.18;
      ring.rotation.y = 0.42;
      ring.position.copy(glassSphere.position);
      rootGroup.add(ring);

      const particles = new THREE.Group();
      for (let index = 0; index < 36; index += 1) {
        const dot = new THREE.Mesh(
          new THREE.SphereGeometry(0.035, 10, 10),
          new THREE.MeshBasicMaterial({
            color: index % 3 === 0 ? 0xff9966 : 0x8ff6e5,
            transparent: true,
            opacity: 0.66,
          }),
        );
        dot.position.set(
          (Math.random() - 0.5) * 8.6,
          (Math.random() - 0.5) * 5.4,
          (Math.random() - 0.5) * 4.2,
        );
        particles.add(dot);
      }
      scene.add(particles);

      const pulsePlane = new THREE.Mesh(
        new THREE.PlaneGeometry(12, 12),
        new THREE.ShaderMaterial({
          transparent: true,
          depthWrite: false,
          uniforms: {
            uTime: { value: 0 },
          },
          vertexShader: `
            varying vec2 vUv;
            void main() {
              vUv = uv;
              gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
          `,
          fragmentShader: `
            varying vec2 vUv;
            uniform float uTime;
            void main() {
              vec2 uv = vUv - 0.5;
              float r = length(uv);
              float wave = sin((r * 18.0) - uTime * 1.6) * 0.5 + 0.5;
              float alpha = smoothstep(0.46, 0.0, r) * wave * 0.08;
              vec3 color = mix(vec3(0.27, 0.85, 0.78), vec3(0.54, 0.66, 1.0), uv.x + 0.5);
              gl_FragColor = vec4(color, alpha);
            }
          `,
        }),
      );
      pulsePlane.position.set(mode === "workspace" ? 3.0 : 2.5, mode === "workspace" ? -0.2 : 0.2, -1.8);
      scene.add(pulsePlane);

      const pointer = { x: 0, y: 0 };
      window.addEventListener("pointermove", (event) => {
        pointer.x = (event.clientX / window.innerWidth) * 2 - 1;
        pointer.y = (event.clientY / window.innerHeight) * 2 - 1;
      });

      const clock = new THREE.Clock();

      const animate = () => {
        const elapsed = clock.getElapsedTime();

        glassSphere.rotation.x = elapsed * 0.18;
        glassSphere.rotation.y = elapsed * 0.24;
        wireOrb.rotation.x = -elapsed * 0.1;
        wireOrb.rotation.y = elapsed * 0.16;
        ring.rotation.z = elapsed * 0.18;
        particles.rotation.y = elapsed * 0.04;
        particles.rotation.x = elapsed * 0.02;
        pulsePlane.material.uniforms.uTime.value = elapsed;

        rootGroup.rotation.x += ((pointer.y * 0.16) - rootGroup.rotation.x) * 0.04;
        rootGroup.rotation.y += ((pointer.x * 0.18) - rootGroup.rotation.y) * 0.04;
        rootGroup.position.y = Math.sin(elapsed * 0.7) * 0.08;

        renderer.render(scene, camera);
        requestAnimationFrame(animate);
      };

      const resize = () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
      };

      window.addEventListener("resize", resize);
      animate();
    })
    .catch(() => {
      canvas.style.display = "none";
    });
}
