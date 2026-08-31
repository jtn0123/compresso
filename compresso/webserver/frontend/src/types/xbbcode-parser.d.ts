declare module 'xbbcode-parser' {
  interface ProcessOptions {
    text: string
    removeMisalignedTags: boolean
    addInLineBreaks: boolean
  }

  interface ProcessResult {
    html: string
    error: boolean
    errorQueue: string[]
  }

  const parser: {
    process(options: ProcessOptions): ProcessResult
  }

  export default parser
}
