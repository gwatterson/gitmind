import { debug } from "../../debug"
import { execFile } from "child_process"

const d = debug("localGetFileAtSHA")

export const localGetFileAtSHA = (path: string, _repo: string | undefined, sha: string) =>
  new Promise<string>((done) => {
    // Use execFile with an argv array (no shell) so that file paths containing
    // shell metacharacters or quotes cannot break out and inject commands.
    const args = ["show", `${sha}:${path}`]
    d(`git ${args.join(" ")}`)

    execFile("git", args, (err, stdout, _stderr) => {
      if (err) {
        console.error(`Could not get the file ${path} from git at ${sha}`)
        console.error(err)
        return
      }

      done(stdout)
    })
  })
