export type ProjectInput = {
  projectFiles: File[];
  projectName: string;
};

const ignoredProjectFolders = new Set(['temp', 'as', 'binaries', 'diagnosis']);

export function projectSourceFiles(files: File[]) {
  return files.filter(file => !(file.webkitRelativePath || file.name)
    .replace(/\\/g, '/').split('/').slice(0, -1)
    .some(part => ignoredProjectFolders.has(part.toLowerCase())));
}

export function appendProjectFiles(form: FormData, {projectFiles, projectName}: ProjectInput) {
  projectSourceFiles(projectFiles).forEach(file => form.append('project_files', file, file.webkitRelativePath || file.name));
  form.append('project_name', projectName || projectFiles[0]?.webkitRelativePath?.split('/')[0] || '');
}
