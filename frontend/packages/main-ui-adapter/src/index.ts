import {
  createMainUiRuntime,
  createSingleGroupLayout,
  defaultTabPresentation,
  type MainUiRuntime,
} from 'main-ui';
import type {Component} from 'vue';

export const WORLD_MODEL_EDITOR_KIND = 'world-model-studio';
export const WORLD_MODEL_RENDERER_KEY = 'world-model-studio-renderer';
export const WORLD_MODEL_WORKSPACE_ID = 'world-model-workspace';

export type RegisterWorldModelOptions = Readonly<{
  editor: Component;
  title?: string;
}>;

/** Register WMK as a consumer-owned editor. This function never creates a main-ui runtime. */
export function registerWorldModelMainUi(runtime: MainUiRuntime, options: RegisterWorldModelOptions): MainUiRuntime {
  const title = options.title ?? 'World Model Studio';
  runtime.core.registerEditor({
    kind: WORLD_MODEL_EDITOR_KIND,
    title,
    description: 'Inspect and control a World Model Kit session',
    icon: 'map',
    rendererKey: WORLD_MODEL_RENDERER_KEY,
    capability: {
      allowCreate: true,
      allowDuplicate: false,
      allowMultipleInstances: false,
      allowMultipleSurfacesPerInstance: false,
      allowClose: false,
      allowReorderInGroup: true,
      allowMoveAcrossGroups: true,
      allowSplitDrop: true,
      allowPopoutWindow: false,
      allowFloatingWindow: false,
      allowModalOverlay: false,
      allowMirrorDisplay: false,
      launcherVisibility: 'hidden-when-opened',
    },
    presentation: defaultTabPresentation,
    availability: {allowedWorkspaceIds: [WORLD_MODEL_WORKSPACE_ID]},
  });
  runtime.core.registerWorkspace({
    id: WORLD_MODEL_WORKSPACE_ID,
    title,
    description: 'World Model Kit interactive workspace',
    icon: 'map',
    allowedEditorKinds: [WORLD_MODEL_EDITOR_KIND],
    recommendedEditorKinds: [WORLD_MODEL_EDITOR_KIND],
    defaultOpenRequests: [{editorKind: WORLD_MODEL_EDITOR_KIND, title}],
    createDefaultLayout: () => createSingleGroupLayout({groupId: 'wmk-group', leafNodeId: 'wmk-leaf'}),
    allowUserReset: true,
  });
  runtime.vue.registerEditorRenderer(WORLD_MODEL_RENDERER_KEY, options.editor);
  return runtime;
}

/** Convenience for standalone apps; SDK packages and adapters do not call this implicitly. */
export function createWorldModelStudioRuntime(options: RegisterWorldModelOptions): MainUiRuntime {
  const runtime = createMainUiRuntime({activeWorkspaceId: WORLD_MODEL_WORKSPACE_ID});
  return registerWorldModelMainUi(runtime, options);
}
