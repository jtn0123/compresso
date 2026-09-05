declare module 'tiny-emitter/instance' {
  interface TinyEmitterInstance {
    on<Args extends unknown[]>(event: string, callback: (...args: Args) => void): TinyEmitterInstance
    once<Args extends unknown[]>(event: string, callback: (...args: Args) => void): TinyEmitterInstance
    off<Args extends unknown[]>(event: string, callback?: (...args: Args) => void): TinyEmitterInstance
    emit<Args extends unknown[]>(event: string, ...args: Args): TinyEmitterInstance
  }

  const emitter: TinyEmitterInstance
  export default emitter
}
