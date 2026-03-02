export interface GenerateOptions { model: string; query: string }
export interface StreamChunk { kind: 'intermediate' | 'confirm' | 'final'; data: unknown }

export async function* generate(opts: GenerateOptions): AsyncGenerator<StreamChunk, void, unknown> {
  // 伪代码：调用后端事件流
  // yield { kind: 'intermediate', data: ... }
  // yield { kind: 'confirm', data: ... } // 等待用户确认后继续
  // yield { kind: 'final', data: ... }   // 可携带跳转信息
}