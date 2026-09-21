import { create } from "zustand";
import type {
  DataMode,
  DataStatus,
  ExplanationResponse,
  HealthResponse,
  AnalyticsSummaryResponse,
  RestrictionListItem,
  RestrictionDetailResponse,
  MatchResponse,
  NetworkImpactResponse,
  MapFeature,
  RouteResponse,
  RouteAvoidMode,
  RoutePicking,
} from "@/lib/types";

interface Filters {
  query: string;
  evaluationStatus: string;
  evidenceConfidence: string;
  impactSeverity: string;
  matchType: string;
  sortKey: string;
  direction: "asc" | "desc";
}

export interface LayerToggles {
  towers: boolean;
  heatmap: boolean;
  buildings: boolean;
}

export type BasemapId = "streets" | "light" | "dark" | "aerial";

interface AccessFlowState {
  restrictions: RestrictionListItem[];
  activeRestrictionId: string | null;
  summary: AnalyticsSummaryResponse | null;
  health: HealthResponse | null;
  mode: DataMode;
  status: DataStatus;
  message: string | null;
  selectedDetail: RestrictionDetailResponse | null;
  selectedMatches: MatchResponse[];
  selectedImpacts: NetworkImpactResponse[];
  page: number;
  mapFeatures: MapFeature[];
  filters: Filters;
  details: Record<string, RestrictionDetailResponse>;
  matches: Record<string, MatchResponse[]>;
  impacts: Record<string, NetworkImpactResponse[]>;
  predictionResult: {
    prediction: string;
    confidence: number;
    probabilities: Record<string, number>;
  } | null;
  predictionLocation: [number, number] | null;
  layerToggles: LayerToggles;
  basemap: BasemapId;
  groundView: boolean;
  isWalking: boolean;
  cameraSignals: { fitEvidence: number; resetView: number };
  walkSignals: { start: number; stop: number };
  routePicking: RoutePicking;
  routeOrigin: [number, number] | null;
  routeDestination: [number, number] | null;
  routeAvoid: RouteAvoidMode;
  route: RouteResponse | null;
  routeLoading: boolean;
  routeError: string | null;
  routeNearbyCount: number;
  walkOverridePath: [number, number][] | null;
  explanation: ExplanationResponse | null;
  explanationLoading: boolean;
  routeExplanation: ExplanationResponse | null;
  overviewExplanation: ExplanationResponse | null;
  overviewOpen: boolean;
  timeFilterHours: number | null;
  isTimePlaying: boolean;

  setExplanation: (explanation: ExplanationResponse | null) => void;
  setExplanationLoading: (loading: boolean) => void;
  setRouteExplanation: (explanation: ExplanationResponse | null) => void;
  setOverviewExplanation: (explanation: ExplanationResponse | null) => void;
  setOverviewOpen: (open: boolean) => void;
  setTimeFilterHours: (hours: number | null) => void;
  setIsTimePlaying: (playing: boolean) => void;
  setRoutePicking: (mode: RoutePicking) => void;
  setRoutePoint: (kind: "origin" | "destination", coords: [number, number]) => void;
  setRouteAvoid: (mode: RouteAvoidMode) => void;
  setRoute: (route: RouteResponse | null) => void;
  setRouteLoading: (loading: boolean) => void;
  setRouteError: (error: string | null) => void;
  setRouteNearbyCount: (count: number) => void;
  clearRoute: () => void;
  setWalkOverridePath: (path: [number, number][] | null) => void;
  setFilters: (patch: Partial<Filters>) => void;
  setPage: (page: number) => void;
  setActiveRestrictionId: (id: string | null) => void;
  setMapFeatures: (features: MapFeature[]) => void;
  setPredictionResult: (result: AccessFlowState["predictionResult"]) => void;
  setPredictionLocation: (coords: [number, number] | null) => void;
  setLayerToggle: (key: keyof LayerToggles, value: boolean) => void;
  setBasemap: (basemap: BasemapId) => void;
  setGroundView: (value: boolean) => void;
  setIsWalking: (value: boolean) => void;
  focusEvidence: () => void;
  resetView: () => void;
  startWalk: () => void;
  stopWalk: () => void;
  clearSelection: () => void;
  loadDashboard: (data: {
    health: HealthResponse | null;
    summary: AnalyticsSummaryResponse | null;
    restrictions: RestrictionListItem[];
    mode: DataMode;
    status: DataStatus;
    message: string | null;
    details?: Record<string, RestrictionDetailResponse>;
    matches?: Record<string, MatchResponse[]>;
    impacts?: Record<string, NetworkImpactResponse[]>;
    mapFeatures?: MapFeature[];
  }) => void;
  setSelected: (data: {
    detail: RestrictionDetailResponse | null;
    matches: MatchResponse[];
    impacts: NetworkImpactResponse[];
    mapFeatures?: MapFeature[];
  }) => void;
  cacheDetail: (
    restrictionId: string,
    detail: RestrictionDetailResponse,
    matches: MatchResponse[],
    impacts: NetworkImpactResponse[],
  ) => void;
}

const initialFilters: Filters = {
  query: "",
  evaluationStatus: "",
  evidenceConfidence: "",
  impactSeverity: "",
  matchType: "",
  sortKey: "restriction_id",
  direction: "asc",
};

export const useStore = create<AccessFlowState>((set) => ({
  restrictions: [],
  activeRestrictionId: null,
  summary: null,
  health: null,
  mode: "live",
  status: "loading",
  message: null,
  selectedDetail: null,
  selectedMatches: [],
  selectedImpacts: [],
  page: 1,
  mapFeatures: [],
  filters: { ...initialFilters },
  details: {},
  matches: {},
  impacts: {},
  predictionResult: null,
  predictionLocation: null,
  layerToggles: { towers: false, heatmap: false, buildings: true },
  basemap: "streets",
  groundView: false,
  isWalking: false,
  cameraSignals: { fitEvidence: 0, resetView: 0 },
  walkSignals: { start: 0, stop: 0 },
  routePicking: null,
  routeOrigin: null,
  routeDestination: null,
  routeAvoid: "none",
  route: null,
  routeLoading: false,
  routeError: null,
  routeNearbyCount: 0,
  walkOverridePath: null,
  explanation: null,
  explanationLoading: false,
  routeExplanation: null,
  overviewExplanation: null,
  overviewOpen: false,
  timeFilterHours: null,
  isTimePlaying: false,

  setExplanation: (explanation) => set({ explanation }),
  setExplanationLoading: (loading) => set({ explanationLoading: loading }),
  setRouteExplanation: (explanation) => set({ routeExplanation: explanation }),
  setOverviewExplanation: (explanation) => set({ overviewExplanation: explanation }),
  setOverviewOpen: (open) => set({ overviewOpen: open }),
  setTimeFilterHours: (hours) => set({ timeFilterHours: hours }),
  setIsTimePlaying: (playing) => set({ isTimePlaying: playing }),

  setRoutePicking: (mode) => set({ routePicking: mode }),

  setRoutePoint: (kind, coords) =>
    set((state) => ({
      routePicking: null,
      routeOrigin: kind === "origin" ? coords : state.routeOrigin,
      routeDestination: kind === "destination" ? coords : state.routeDestination,
    })),

  setRouteAvoid: (mode) => set({ routeAvoid: mode }),

  setRoute: (route) => set({ route, routeError: null }),

  setRouteLoading: (loading) => set({ routeLoading: loading }),

  setRouteError: (error) => set({ routeError: error, route: null }),

  setRouteNearbyCount: (count) => set({ routeNearbyCount: count }),

  clearRoute: () =>
    set({
      routePicking: null,
      routeOrigin: null,
      routeDestination: null,
      route: null,
      routeError: null,
      routeNearbyCount: 0,
      walkOverridePath: null,
      routeExplanation: null,
    }),

  setWalkOverridePath: (path) => set({ walkOverridePath: path }),

  setFilters: (patch) =>
    set((state) => ({
      filters: { ...state.filters, ...patch },
      page: 1,
    })),

  setPage: (page) => set({ page }),

  setActiveRestrictionId: (id) => set({ activeRestrictionId: id }),

  setMapFeatures: (features) => set({ mapFeatures: features }),

  setPredictionResult: (result) => set({ predictionResult: result }),

  setPredictionLocation: (coords) => set({ predictionLocation: coords }),

  setLayerToggle: (key, value) =>
    set((state) => ({
      layerToggles: { ...state.layerToggles, [key]: value },
    })),

  setBasemap: (basemap) => set({ basemap }),

  setGroundView: (value) => set({ groundView: value }),

  setIsWalking: (value) => set({ isWalking: value }),

  focusEvidence: () =>
    set((s) => ({
      cameraSignals: { ...s.cameraSignals, fitEvidence: s.cameraSignals.fitEvidence + 1 },
    })),

  resetView: () =>
    set((s) => ({
      cameraSignals: { ...s.cameraSignals, resetView: s.cameraSignals.resetView + 1 },
    })),

  startWalk: () =>
    set((s) => ({
      walkSignals: { ...s.walkSignals, start: s.walkSignals.start + 1 },
    })),

  stopWalk: () =>
    set((s) => ({
      walkSignals: { ...s.walkSignals, stop: s.walkSignals.stop + 1 },
    })),

  clearSelection: () =>
    set({
      activeRestrictionId: null,
      selectedDetail: null,
      selectedMatches: [],
      selectedImpacts: [],
      explanation: null,
    }),

  loadDashboard: (data) =>
    set({
      health: data.health,
      summary: data.summary,
      restrictions: data.restrictions,
      mode: data.mode,
      status: data.status,
      message: data.message,
      details: data.details ?? {},
      matches: data.matches ?? {},
      impacts: data.impacts ?? {},
      mapFeatures: data.mapFeatures ?? [],
      activeRestrictionId: null,
      selectedDetail: null,
      selectedMatches: [],
      selectedImpacts: [],
      page: 1,
    }),

  setSelected: (data) =>
    set({
      selectedDetail: data.detail,
      selectedMatches: data.matches,
      selectedImpacts: data.impacts,
      mapFeatures: data.mapFeatures ?? [],
    }),

  cacheDetail: (restrictionId, detail, matches, impacts) =>
    set((state) => ({
      details: { ...state.details, [restrictionId]: detail },
      matches: { ...state.matches, [restrictionId]: matches },
      impacts: { ...state.impacts, [restrictionId]: impacts },
    })),
}));
