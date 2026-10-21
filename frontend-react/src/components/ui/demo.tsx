"use client";
import NoteGraph, { type Note } from "@/components/ui/note-graph";
import * as React from "react";

const notes: Note[] = [
  { id: "index", title: "Project Index", group: "projects" },
  { id: "roadmap", title: "Roadmap", group: "projects" },
  { id: "architecture", title: "Architecture", group: "projects" },
  { id: "api-notes", title: "API Notes", group: "projects" },
  { id: "onboarding", title: "Onboarding", group: "projects" },
  { id: "reading-list", title: "Reading List", group: "reading" },
  {
    id: "systems-book",
    title: "Designing Data-Intensive Apps",
    group: "reading",
  },
  { id: "paper-raft", title: "Raft Paper", group: "reading" },
  { id: "paper-crdt", title: "CRDT Paper", group: "reading" },
  { id: "idea-cache", title: "Idea Cache", group: "reading" },
  { id: "journal-mon", title: "Monday standup", group: "journal" },
  { id: "journal-tue", title: "Tuesday notes", group: "journal" },
  { id: "journal-wed", title: "Wednesday notes", group: "journal" },
  { id: "retro", title: "Sprint retro", group: "journal" },
  { id: "old-draft", title: "Old draft" },
  { id: "random-link", title: "Random link dump" },
  { id: "contact-list", title: "Contact list" },
];

const links = [
  { source: "index", target: "roadmap" },
  { source: "index", target: "architecture" },
  { source: "index", target: "api-notes" },
  { source: "index", target: "onboarding" },
  { source: "roadmap", target: "retro" },
  { source: "architecture", target: "api-notes" },
  { source: "architecture", target: "systems-book" },
  { source: "onboarding", target: "journal-mon" },
  { source: "reading-list", target: "systems-book" },
  { source: "reading-list", target: "paper-raft" },
  { source: "reading-list", target: "paper-crdt" },
  { source: "systems-book", target: "paper-raft" },
  { source: "paper-raft", target: "paper-crdt" },
  { source: "journal-mon", target: "journal-tue" },
  { source: "journal-tue", target: "journal-wed" },
  { source: "journal-wed", target: "retro" },
  { source: "retro", target: "idea-cache" },
  { source: "idea-cache", target: "reading-list" },
];

export default function NoteGraphDemo() {
  const [selectedId, setSelectedId] = React.useState<string | undefined>();

  return (
    <div className="bg-background text-foreground flex h-full w-full items-center justify-center p-4">
      <NoteGraph
        notes={notes}
        links={links}
        selectedId={selectedId}
        onSelect={(note) => setSelectedId(note.id)}
        height={520}
        className="w-full max-w-4xl"
      />
    </div>
  );
}
