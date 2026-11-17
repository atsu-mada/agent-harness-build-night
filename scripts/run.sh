#!/bin/sh
# Run a command of this project with the Neo4j password in NEO4J_PASSWORD.
# The key is decrypted by api_secrets (~/Python/01_obsidian_management) and passed
# only to the child process; it is never printed or written to a file.
#
#   scripts/run.sh                 # Gradio app
#   scripts/run.sh probe           # Neo4j connection test (one CC_Probe node, deleted)
#   scripts/run.sh aiand           # ai& backup LLM self-test (key aiand_api_key only)
#   scripts/run.sh aiand-models    # list ai& model ids
#   scripts/run.sh -- <command>    # any command, run in the repository root
#   WITH_AIAND=1 scripts/run.sh    # app with both NEO4J_PASSWORD and AIAND_API_KEY
set -eu
REPO=$(cd "$(dirname "$0")/.." && pwd)
SECRETS=${OBSIDIAN_MANAGEMENT_ROOT:-$HOME/Python/01_obsidian_management}
cd "$REPO"
need_key() {  # stop with the registration command when a key is not registered yet
  [ -f "$SECRETS/config/browser_auth/path_config/$1/credential_ref.json" ] && return 0
  echo "key $1 is not registered. Register it (hidden input):" >&2
  echo "  cd $SECRETS && uv run --frozen python -m api_secrets.register --key-id $1 --domain $2" >&2
  exit 3
}
RUN_KEY="uv run --project $SECRETS --frozen python -m api_secrets.run_with_key"
case "${1:-}" in
  aiand|aiand-models)
    need_key aiand_api_key api.aiand.com
    [ "$1" = aiand ] && arg= || arg=models
    exec $RUN_KEY --key-id aiand_api_key --env AIAND_API_KEY -- \
      env -u VIRTUAL_ENV uv run --project "$REPO" python src/continuity_checker/llm_aiand.py $arg ;;
esac
case "${1:-app}" in
  app)   set -- uv run --project "$REPO" python src/continuity_checker/app.py ;;
  probe) set -- uv run --project "$REPO" python src/continuity_checker/neo4j_store.py ;;
  --)    shift ;;
  *)     echo "usage: scripts/run.sh [app|probe|-- command]" >&2; exit 2 ;;
esac
# env -u: the outer uv run sets VIRTUAL_ENV to the api_secrets project; drop it so the
# inner uv run uses this project's .venv.
need_key neo4j_local_password localhost
if [ "${WITH_AIAND:-0}" = 1 ]; then
  need_key aiand_api_key api.aiand.com
  set -- $RUN_KEY --key-id aiand_api_key --env AIAND_API_KEY -- env -u VIRTUAL_ENV "$@"
fi
exec $RUN_KEY --key-id neo4j_local_password --env NEO4J_PASSWORD -- env -u VIRTUAL_ENV "$@"
