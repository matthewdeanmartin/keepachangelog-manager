// Minimal ambient types for the parts of the File System Access API this app
// uses. The bundled TS DOM lib does not declare `showDirectoryPicker`, so we
// augment Window here. See spec/web_remaining_phases.md §4 (W1c).

interface Window {
  showDirectoryPicker(options?: {
    mode?: 'read' | 'readwrite';
  }): Promise<FileSystemDirectoryHandle>;
}
