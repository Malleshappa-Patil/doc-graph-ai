import { useEffect, useRef, useState, useCallback } from "react";
import type { Note } from "@/components/ui/note-graph";

export type ForceLink = {
  source: string;
  target: string;
};

export type NodePosition = {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  pinned?: boolean;
};

/**
 * Force-directed layout hook for NoteGraph.
 * Simulates Coulomb repulsion, Hooke link attraction, centering gravity,
 * and handles dragging / pinning with smooth settling.
 */
export function useForceGraph(
  notes: Note[],
  links: ForceLink[],
  size: { width: number; height: number },
) {
  const [positions, setPositions] = useState<{ id: string; x: number; y: number }[]>([]);
  const simRef = useRef<Map<string, NodePosition>>(new Map());
  const pinnedRef = useRef<Set<string>>(new Set());
  const animFrameRef = useRef<number | null>(null);

  // Initialize or reconcile node positions
  useEffect(() => {
    const currentMap = simRef.current;
    const newMap = new Map<string, NodePosition>();
    const cx = size.width / 2;
    const cy = size.height / 2;
    const radius = Math.min(size.width, size.height) * 0.35;

    // Identify orphan notes vs connected notes
    const connectedIds = new Set<string>();
    for (const link of links) {
      connectedIds.add(link.source);
      connectedIds.add(link.target);
    }

    const orphanNotes = notes.filter((n) => !connectedIds.has(n.id));
    const linkedNotes = notes.filter((n) => connectedIds.has(n.id));

    // Place linked notes in a cluster near center with small random jitter
    linkedNotes.forEach((note, i) => {
      const existing = currentMap.get(note.id);
      if (existing) {
        newMap.set(note.id, existing);
      } else {
        const angle = (i / Math.max(1, linkedNotes.length)) * Math.PI * 2;
        const dist = Math.random() * (radius * 0.6);
        newMap.set(note.id, {
          id: note.id,
          x: cx + Math.cos(angle) * dist,
          y: cy + Math.sin(angle) * dist,
          vx: 0,
          vy: 0,
        });
      }
    });

    // Place orphan notes in a ring around the perimeter
    orphanNotes.forEach((note, i) => {
      const existing = currentMap.get(note.id);
      if (existing) {
        newMap.set(note.id, existing);
      } else {
        const ringRadius = radius * 1.15;
        const angle = (i / Math.max(1, orphanNotes.length)) * Math.PI * 2;
        newMap.set(note.id, {
          id: note.id,
          x: cx + Math.cos(angle) * ringRadius,
          y: cy + Math.sin(angle) * ringRadius,
          vx: 0,
          vy: 0,
        });
      }
    });

    simRef.current = newMap;

    // Simulation loop
    let alpha = 1.0;
    const minAlpha = 0.005;
    const decay = 0.985;

    function step() {
      if (alpha < minAlpha) {
        // Settled: update state once more and stop loop
        setPositions(Array.from(simRef.current.values()).map(({ id, x, y }) => ({ id, x, y })));
        return;
      }

      const nodes = Array.from(simRef.current.values());
      const nodeCount = nodes.length;
      if (nodeCount === 0) return;

      // 1. Repulsion between all nodes
      for (let i = 0; i < nodeCount; i++) {
        const a = nodes[i];
        for (let j = i + 1; j < nodeCount; j++) {
          const b = nodes[j];
          let dx = b.x - a.x;
          let dy = b.y - a.y;
          let distSq = dx * dx + dy * dy;
          if (distSq < 1) {
            dx = (Math.random() - 0.5) * 2;
            dy = (Math.random() - 0.5) * 2;
            distSq = 1;
          }
          const dist = Math.sqrt(distSq);
          const force = (800 / (distSq + 100)) * alpha;

          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;

          if (!pinnedRef.current.has(a.id)) {
            a.vx -= fx;
            a.vy -= fy;
          }
          if (!pinnedRef.current.has(b.id)) {
            b.vx += fx;
            b.vy += fy;
          }
        }
      }

      // 2. Attraction along links
      for (const link of links) {
        const a = simRef.current.get(link.source);
        const b = simRef.current.get(link.target);
        if (!a || !b) continue;

        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const targetDist = 70;
        const force = ((dist - targetDist) * 0.045) * alpha;

        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        if (!pinnedRef.current.has(a.id)) {
          a.vx += fx;
          a.vy += fy;
        }
        if (!pinnedRef.current.has(b.id)) {
          b.vx -= fx;
          b.vy -= fy;
        }
      }

      // 3. Center gravity & boundary dampening
      const pad = 30;
      for (const node of nodes) {
        if (pinnedRef.current.has(node.id)) continue;

        // Centering force
        node.vx += ((cx - node.x) * 0.015) * alpha;
        node.vy += ((cy - node.y) * 0.015) * alpha;

        // Apply velocities with damping
        node.vx *= 0.85;
        node.vy *= 0.85;

        node.x += node.vx;
        node.y += node.vy;

        // Keep inside bounds
        node.x = Math.max(pad, Math.min(size.width - pad, node.x));
        node.y = Math.max(pad, Math.min(size.height - pad, node.y));
      }

      alpha *= decay;
      setPositions(nodes.map(({ id, x, y }) => ({ id, x, y })));
      animFrameRef.current = requestAnimationFrame(step);
    }

    animFrameRef.current = requestAnimationFrame(step);

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [notes, links, size.width, size.height]);

  const drag = useCallback((id: string, x: number, y: number) => {
    pinnedRef.current.add(id);
    const node = simRef.current.get(id);
    if (node) {
      node.x = x;
      node.y = y;
      node.vx = 0;
      node.vy = 0;
      setPositions(Array.from(simRef.current.values()).map((n) => ({ id: n.id, x: n.x, y: n.y })));
    }
  }, []);

  const release = useCallback((id: string) => {
    pinnedRef.current.delete(id);
  }, []);

  return { positions, drag, release };
}
