import React, { useState, useEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { EffectComposer, Bloom } from '@react-three/postprocessing'
import * as THREE from 'three'
import { UMAP } from 'umap-js'

// TRON color palette
const COLORS = {
  electricBlue: '#00d9ff',
  hotOrange: '#ff6600',
  darkBlue: '#003d5c',
  black: '#000000',
  glowBlue: '#00ffff',
  additiveOrange: '#ff8833', // Orange with some blue mixed in for proper white hotspots
}

function FloorGrid() {
  // Use Three.js GridHelper for a proper grid
  const size = 20
  const divisions = 20
  
  return (
    <gridHelper args={[size, divisions, COLORS.electricBlue, COLORS.electricBlue]} rotation={[0, 0, 0]}>
      <lineBasicMaterial 
        color={COLORS.electricBlue} 
        opacity={0.3} 
        transparent 
        attach="material"
      />
    </gridHelper>
  )
}

function MemoryDot({ position, memory, onHover, onClick, onDoubleClick, scale = 1 }) {
  const meshRef = useRef()
  const [hovered, setHovered] = useState(false)
  
  useFrame((state) => {
    if (meshRef.current && hovered) {
      // Pulse effect when hovered
      meshRef.current.scale.setScalar(1 + Math.sin(state.clock.elapsedTime * 4) * 0.2)
    }
  })

  return (
    <mesh
      ref={meshRef}
      position={position}
      onPointerOver={(e) => {
        e.stopPropagation()
        setHovered(true)
        onHover(memory)
      }}
      onPointerOut={(e) => {
        e.stopPropagation()
        setHovered(false)
        onHover(null)
      }}
      onClick={(e) => {
        e.stopPropagation()
        onClick(memory)
      }}
      onDoubleClick={(e) => {
        e.stopPropagation()
        onDoubleClick(position)
      }}
    >
      <sphereGeometry args={[0.016 * scale, 8, 8]} />
      <meshBasicMaterial 
        color={hovered ? [0, 1.2, 1.5] : [1.5, 0.7, 0.2]}
        transparent={false}
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
    </mesh>
  )
}

function MemoryCloud({ memories, onHover, onClick, onDoubleClick, pointScale }) {
  const [positions, setPositions] = useState([])

  useEffect(() => {
    if (memories.length === 0) return

    console.log('Processing', memories.length, 'memories')
    
    // Extract embeddings - filter out any without embeddings
    const validMemories = memories.filter(m => m.embedding && m.embedding.length === 768)
    console.log('Valid memories with embeddings:', validMemories.length)
    
    if (validMemories.length === 0) {
      console.warn('No memories with valid embeddings!')
      return
    }
    
    const embeddings = validMemories.map(m => m.embedding)
    
    // Use UMAP to reduce dimensions from 768 to 3
    const umap = new UMAP({
      nComponents: 3,
      nNeighbors: Math.min(15, Math.floor(validMemories.length / 20)), // Balance local and global structure
      minDist: 0.1,  // Allow tighter clusters
      spread: 1.0,   // Standard spread for natural clustering
      // Note: UMAP.js doesn't support seed parameter, will be non-deterministic
    })

    console.log('Running UMAP on', embeddings.length, 'memories...')
    try {
      const projection = umap.fit(embeddings)
      console.log('UMAP projection complete:', projection.length, 'points')
      
      // Calculate centroid to center the cloud at origin
      const centroid = projection.reduce(
        (acc, [x, y, z]) => [acc[0] + x, acc[1] + y, acc[2] + z],
        [0, 0, 0]
      ).map(v => v / projection.length)
      
      // Center and scale the 3D positions
      const positions3D = projection.map(([x, y, z]) => {
        // Center around origin by subtracting centroid
        const centered = [x - centroid[0], y - centroid[1], z - centroid[2]]
        // Scale to fill our 3D space nicely
        const scale = 3.0;
        return [centered[0] * scale, centered[1] * scale, centered[2] * scale]
      })
      
      console.log('3D positions:', positions3D.length)
      setPositions(positions3D)
    } catch (error) {
      console.error('UMAP failed:', error)
    }
  }, [memories])

  return (
    <>
      {memories.map((memory, i) => 
        positions[i] && (
          <MemoryDot
            key={memory.id}
            position={positions[i]}
            memory={memory}
            onHover={onHover}
            onClick={onClick}
            onDoubleClick={onDoubleClick}
            scale={pointScale}
          />
        )
      )}
    </>
  )
}

function WASDControls({ controlsRef }) {
  const { camera } = useThree()
  const moveSpeed = 0.025
  
  useEffect(() => {
    const keys = {}
    
    const handleKeyDown = (e) => {
      keys[e.key.toLowerCase()] = true
    }
    
    const handleKeyUp = (e) => {
      keys[e.key.toLowerCase()] = false
    }
    
    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('keyup', handleKeyUp)
    
    const interval = setInterval(() => {
      if (!controlsRef.current) return
      
      // Get camera's forward direction
      const forward = new THREE.Vector3()
      camera.getWorldDirection(forward)
      forward.y = 0 // Keep movement horizontal
      forward.normalize()
      
      // Get camera's right direction
      const right = new THREE.Vector3()
      right.crossVectors(forward, new THREE.Vector3(0, 1, 0))
      right.normalize()
      
      // Move camera AND orbit target together
      const movement = new THREE.Vector3()
      
      if (keys['w']) {
        movement.addScaledVector(forward, moveSpeed)
      }
      if (keys['s']) {
        movement.addScaledVector(forward, -moveSpeed)
      }
      if (keys['a']) {
        movement.addScaledVector(right, -moveSpeed)
      }
      if (keys['d']) {
        movement.addScaledVector(right, moveSpeed)
      }
      if (keys['r']) {
        movement.y += moveSpeed
      }
      if (keys['f']) {
        movement.y -= moveSpeed
      }
      
      // Move both camera and target to maintain orientation
      camera.position.add(movement)
      controlsRef.current.target.add(movement)
      controlsRef.current.update()
    }, 16) // ~60fps
    
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('keyup', handleKeyUp)
      clearInterval(interval)
    }
  }, [camera, controlsRef])
  
  return null
}

function Scene({ memories, onHover, onClick, pointScale, bloomIntensity }) {
  const controlsRef = useRef()
  
  const handleDoubleClick = (position) => {
    if (controlsRef.current) {
      // Set the orbit target to the memory position
      controlsRef.current.target.set(position[0], position[1], position[2])
      controlsRef.current.update()
    }
  }
  
  return (
    <>
      <color attach="background" args={['#000000']} />
      <ambientLight intensity={0.1} />
      <FloorGrid />
      <MemoryCloud memories={memories} onHover={onHover} onClick={onClick} onDoubleClick={handleDoubleClick} pointScale={pointScale} />
      <WASDControls controlsRef={controlsRef} />
      <OrbitControls 
        ref={controlsRef}
        enablePan={true}
        enableZoom={true}
        minDistance={1}
        maxDistance={50}
        rotateSpeed={0.5}
        panSpeed={0.5}
      />
      <EffectComposer multisampling={0}>
        <Bloom 
          intensity={bloomIntensity}
          kernelSize={4}
          luminanceThreshold={0.05}
          luminanceSmoothing={0.3}
          radius={0.5}
          mipmapBlur
        />
      </EffectComposer>
    </>
  )
}

export default function App() {
  const [apiKey, setApiKey] = useState('')
  const [showApiKey, setShowApiKey] = useState(false)
  const [authenticated, setAuthenticated] = useState(false)
  const [memories, setMemories] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [hoveredMemory, setHoveredMemory] = useState(null)
  const [selectedMemory, setSelectedMemory] = useState(null)
  const [pointScale, setPointScale] = useState(1)
  const [bloomIntensity, setBloomIntensity] = useState(5)

  const handleAuthenticate = async () => {
    console.log('Authenticating with key:', apiKey.substring(0, 10) + '...')
    setLoading(true)
    setError(null)
    
    try {
      const response = await fetch('/api/v1/vectors', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': apiKey,
        },
        body: JSON.stringify({ limit: 6000 }),
      })

      if (response.ok) {
        const data = await response.json()
        console.log(`Success! Loaded ${data.memories.length} memories`)
        setMemories(data.memories)
        setAuthenticated(true)
      } else if (response.status === 401) {
        setError('Invalid API key')
      } else {
        setError(`Error: ${response.statusText}`)
      }
    } catch (err) {
      console.error('Error authenticating:', err)
      setError('Failed to connect to server')
    }
    
    setLoading(false)
  }

  // Authentication screen
  if (!authenticated) {
    return (
      <div style={{
        width: '100vw',
        height: '100vh',
        background: COLORS.black,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      }}>
        <div style={{
          padding: '40px',
          maxWidth: '480px',
          width: '90%',
        }}>
          <div style={{
            position: 'relative',
            marginBottom: '16px',
          }}>
            <input
              type={showApiKey ? 'text' : 'password'}
              placeholder="pond_sk_..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && !loading && apiKey && handleAuthenticate()}
              autoFocus
              style={{
                width: '100%',
                padding: '14px 48px 14px 16px',
                background: 'rgba(255, 255, 255, 0.05)',
                border: `1px solid rgba(0, 217, 255, 0.3)`,
                borderRadius: '4px',
                color: '#ffffff',
                fontSize: '14px',
                fontFamily: 'monospace',
                outline: 'none',
                boxSizing: 'border-box',
                transition: 'border-color 0.2s',
              }}
              onFocus={(e) => e.target.style.borderColor = 'rgba(0, 217, 255, 0.6)'}
              onBlur={(e) => e.target.style.borderColor = 'rgba(0, 217, 255, 0.3)'}
            />
            <button
              type="button"
              onClick={() => setShowApiKey(!showApiKey)}
              style={{
                position: 'absolute',
                right: '12px',
                top: '50%',
                transform: 'translateY(-50%)',
                background: 'transparent',
                border: 'none',
                color: 'rgba(0, 217, 255, 0.6)',
                cursor: 'pointer',
                padding: '4px',
                fontSize: '18px',
                fontFamily: 'system-ui',
              }}
            >
              {showApiKey ? '👁' : '👁‍🗨'}
            </button>
          </div>
          
          <button
            onClick={handleAuthenticate}
            disabled={loading || !apiKey}
            style={{
              width: '100%',
              padding: '14px',
              background: loading ? 'rgba(0, 217, 255, 0.1)' : 'rgba(0, 217, 255, 0.15)',
              border: `1px solid ${loading ? 'rgba(0, 217, 255, 0.2)' : 'rgba(0, 217, 255, 0.4)'}`,
              borderRadius: '4px',
              color: loading ? 'rgba(0, 217, 255, 0.5)' : COLORS.electricBlue,
              fontSize: '14px',
              fontFamily: 'inherit',
              fontWeight: '500',
              cursor: loading || !apiKey ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s',
              opacity: !apiKey ? 0.5 : 1,
            }}
          >
            {loading ? 'Authenticating...' : 'Connect'}
          </button>
          
          {error && (
            <div style={{
              marginTop: '16px',
              padding: '12px',
              background: 'rgba(255, 102, 0, 0.1)',
              border: `1px solid rgba(255, 102, 0, 0.3)`,
              borderRadius: '4px',
              color: COLORS.hotOrange,
              fontSize: '13px',
              textAlign: 'center',
            }}>
              {error}
            </div>
          )}
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div style={{
        width: '100vw',
        height: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: COLORS.electricBlue,
        fontSize: '14px',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        background: COLORS.black,
      }}>
        Loading memories...
      </div>
    )
  }

  return (
    <div style={{ width: '100vw', height: '100vh', background: COLORS.black, position: 'relative' }}>
      <Canvas 
        camera={{ position: [8, 4, 8], fov: 50 }}
        gl={{ 
          antialias: true,
          toneMapping: THREE.ACESFilmicToneMapping,
          outputColorSpace: THREE.SRGBColorSpace
        }}
      >
        <Scene memories={memories} onHover={setHoveredMemory} onClick={setSelectedMemory} pointScale={pointScale} bloomIntensity={bloomIntensity} />
      </Canvas>
      
      {/* Hover tooltip */}
      {hoveredMemory && (
        <div style={{
          position: 'absolute',
          top: '20px',
          left: '20px',
          right: '20px',
          color: COLORS.electricBlue,
          fontSize: '10px',
          fontFamily: 'Courier New, monospace',
          textShadow: `0 0 10px ${COLORS.electricBlue}`,
          pointerEvents: 'none',
          opacity: 0.7,
          maxHeight: '100px',
          overflow: 'hidden',
        }}>
          {hoveredMemory.content.substring(0, 200)}...
        </div>
      )}

      {/* Selected memory panel */}
      {selectedMemory && (
        <div style={{
          position: 'absolute',
          bottom: '20px',
          left: '20px',
          right: '20px',
          maxHeight: '200px',
          padding: '15px',
          background: `rgba(0, 0, 0, 0.8)`,
          border: `1px solid ${COLORS.electricBlue}`,
          color: COLORS.electricBlue,
          fontSize: '12px',
          fontFamily: 'Courier New, monospace',
          overflow: 'auto',
          cursor: 'pointer',
        }}
        onClick={() => setSelectedMemory(null)}
        >
          <div style={{ marginBottom: '10px', opacity: 0.5, fontSize: '10px' }}>
            {new Date(selectedMemory.created_at).toLocaleString()}
          </div>
          {selectedMemory.content}
        </div>
      )}
      
      {/* Control Panel */}
      <div style={{
        position: 'absolute',
        top: '20px',
        right: '20px',
        background: 'rgba(0, 0, 0, 0.7)',
        border: `1px solid ${COLORS.electricBlue}`,
        borderRadius: '4px',
        padding: '15px',
        width: '200px',
        color: COLORS.electricBlue,
        fontSize: '11px',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      }}>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', opacity: 0.7 }}>
            Point Size
          </label>
          <input
            type="range"
            min="0.5"
            max="3"
            step="0.1"
            value={pointScale}
            onChange={(e) => setPointScale(parseFloat(e.target.value))}
            style={{
              width: '100%',
              accentColor: COLORS.electricBlue,
            }}
          />
        </div>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', opacity: 0.7 }}>
            Glow Intensity
          </label>
          <input
            type="range"
            min="5"
            max="50"
            step="1"
            value={bloomIntensity}
            onChange={(e) => setBloomIntensity(parseFloat(e.target.value))}
            style={{
              width: '100%',
              accentColor: COLORS.electricBlue,
            }}
          />
        </div>
        <div style={{ 
          paddingTop: '10px', 
          borderTop: `1px solid ${COLORS.electricBlue}33`,
          opacity: 0.5,
          fontSize: '10px',
        }}>
          {memories.length} memories<br/>
          WASD+RF to move • Mouse to orbit
        </div>
      </div>
    </div>
  )
}