const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("opensore", {
  selectSources: () => ipcRenderer.invoke("dialog:openSources"),
  selectOutput: () => ipcRenderer.invoke("dialog:selectOutput"),
  openPath: (targetPath) => ipcRenderer.invoke("shell:openPath", targetPath),
  planDiscovery: (request) => ipcRenderer.invoke("opensore:planDiscovery", request),
  runDiscovery: (payload) => ipcRenderer.invoke("opensore:runDiscovery", payload),
});
