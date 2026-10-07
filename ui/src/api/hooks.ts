import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "./client"

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 15_000,
    retry: false,
  })
}

export function useGraph() {
  return useQuery({ queryKey: ["graph"], queryFn: api.graph })
}

export function useGuarantees() {
  return useQuery({ queryKey: ["guarantees"], queryFn: api.guarantees })
}

export function useScenarios() {
  return useQuery({ queryKey: ["scenarios"], queryFn: api.scenarios })
}

export function useRunScenario() {
  return useMutation({ mutationFn: api.runScenario })
}

export function useEvaluation() {
  return useQuery({
    queryKey: ["evaluation"],
    queryFn: api.evaluation,
    staleTime: Infinity, // the backend caches this for ~100s of compute; don't refetch idly
  })
}

export function useRefreshEvaluation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.refreshEvaluation,
    onSuccess: (data) => queryClient.setQueryData(["evaluation"], data),
  })
}
