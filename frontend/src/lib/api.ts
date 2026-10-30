import axios from 'axios'
import type { Capability, HealthResponse } from '@/types/api'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5200',
  timeout: 8000,
})

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>('/api/v1/health')
  return data
}

export async function getCapabilities(): Promise<Capability[]> {
  const { data } = await api.get<Capability[]>('/api/v1/capabilities')
  return data
}

