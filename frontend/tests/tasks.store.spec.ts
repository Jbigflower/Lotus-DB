import { describe, it, expect } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useTasksStore } from '@/stores/tasks'
import { TaskStatus, TaskPriority } from '@/types/task'

describe('useTasksStore sorting and progress', () => {
  it('computes progress percent and sorts by status', () => {
    setActivePinia(createPinia())
    const store = useTasksStore()
    store.list = [
      { id: 'a', name: 'A', description: '', task_type: 0 as any, sub_type: 0 as any, priority: TaskPriority.NORMAL, parameters: {}, status: TaskStatus.RUNNING, progress: { current_step: '', total_steps: 10, completed_steps: 5 }, result: {}, created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
      { id: 'b', name: 'B', description: '', task_type: 0 as any, sub_type: 0 as any, priority: TaskPriority.LOW, parameters: {}, status: TaskStatus.COMPLETED, progress: { current_step: '', total_steps: 10, completed_steps: 10 }, result: {}, created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
    ] as any
    expect(Math.round(store.progressPercentById['a'] * 100)).toBe(50)
    store.setSort('status', 'desc')
    const sorted = store.sortedList
    expect(sorted[0].status).toBe(TaskStatus.RUNNING)
  })
})

