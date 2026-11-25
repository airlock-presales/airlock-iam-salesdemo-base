# Waiting period of the account recovery (phase D)
#
# Method "waiting period" (10 points): offered with more points than the known browser alone gives. Choosing it
# saves the state with the user (context data recovery_state: JSON with the round and the points of the methods
# done; recovery_wait_until: epoch seconds), emails the user and ends the flow. At the next recovery the restore
# script (after password, email code and known browser) reads the state:
# - waiting period over: the methods done count again (plus 10 points for waiting), continue with the next round
# - still waiting: continue in the round where the wait started; the option "come back later" ends the flow
# - no state, or ended more than MAX_AGE ago: start from scratch
# The restore script writes its own namespace (recovery-restore): keys <method>Done / <method>Points only for the
# methods done, skipR<n> for the rounds to skip; the "done" conditions and the sum script read it too.
# Cancel: a normal login deletes the state (step in the login flow); also deleted after the recovery succeeded or
# was not possible.

WAIT_MINUTES = 5
WAIT_POINTS = 10
KNOWN_BROWSER_POINTS = 10
MAX_AGE_HOURS = 24


def restore_script(method_keys, rounds):
    """method_keys: lower-camel keys of the METHODS (e.g. emailAlt)"""
    return r'''-- account recovery: continue a saved recovery (waiting period) - context data recovery_state / recovery_wait_until
local MAX_AGE = %d * 3600
local WAIT_POINTS = %d
local ROUNDS = %d
function iam_on_step_init ()
    local out = { resumed = false, pending = false, expired = false, minutesLeft = "0", untilIso = "", untilUtc = "" }
    for r = 1, ROUNDS do out["skipR" .. r] = false end
    local raw = iam.input_map["recovery_state"]
    local untilTime = tonumber(iam.input_map["recovery_wait_until"] or "")
    if type(raw) ~= "string" or raw == "" or not untilTime then return out end
    local now = os.time()
    if now > untilTime + MAX_AGE then
        iam.log:info("Recovery: saved state of " .. tostring(iam.input_map["user-id"]) .. " too old - starting from scratch")
        return out
    end
    local ok, state = pcall(iam.cjson.decode, raw)
    if not ok or type(state) ~= "table" then return out end
    out.resumed = true
    for key, points in pairs(state.points or {}) do
        out[key .. "Done"] = true
        out[key .. "Points"] = tostring(points)
    end
    local round = tonumber(state.round) or 1
    if now >= untilTime then
        out.expired = true
        out.waitDone = true
        out.waitPoints = tostring(WAIT_POINTS)
        round = round + 1
    else
        out.pending = true
        out.minutesLeft = tostring(math.ceil((untilTime - now) / 60))
        -- end of the wait for the text: UTC (the design kit shows it in the browser's time zone, iam-custom.js)
        out.untilIso = os.date("!%%Y-%%m-%%dT%%H:%%M:%%SZ", untilTime)
        out.untilUtc = os.date("!%%H:%%M", untilTime) .. " UTC"
    end
    for r = 1, ROUNDS do out["skipR" .. r] = r < round end
    iam.log:info("Recovery: " .. tostring(iam.input_map["user-id"]) .. " continues in round " .. round .. (out.expired and " (waiting period over)" or " (still waiting)"))
    return out
end''' % (MAX_AGE_HOURS, WAIT_POINTS, rounds)


def start_script(method_keys, r):
    keys = ', '.join('"%s"' % k for k in method_keys if k != 'wait')
    return r'''-- account recovery: start the waiting period - state to save (round, points of the methods done), end of the wait
local MINUTES = %d
local ROUND = %d
local KEYS = { %s }
function iam_on_step_init ()
    local points = {}
    for _, key in ipairs(KEYS) do
        if iam.input_map[key .. "Done"] == true or iam.input_map[key .. "Done"] == "true" then
            points[key] = tonumber(iam.input_map[key .. "Points"]) or 0
        end
    end
    local state = iam.cjson.encode({ round = ROUND, points = points })
    iam.log:info("Recovery: waiting period started by " .. tostring(iam.input_map["user-id"]) .. ", state " .. state)
    return { state = state, waitUntil = tostring(os.time() + MINUTES * 60), minutes = tostring(MINUTES) }
end''' % (WAIT_MINUTES, r, keys)


# ------------------------------------------------------------------ YAML builders (blk/output/... passed in by generate.py)
RESTORE_RESULT_DEF = """type: ScriptExecutionResultValueMapProvider
id: recoveryRestoreResult
displayName: Recovery - Saved State (restored points, rounds to skip, waiting period)
properties:
  namespaceConfig:
    ref: recoveryRestoreNamespace"""

WAIT_AVAILABLE_DEF = """type: LogicalAndFlowCondition
id: recoveryWaitAvailable
displayName: Recovery - Waiting Period Available (more than %d points, not already waiting)
properties:
  conditions:
  - pluginList:
    - type: BooleanCondition
      id: recoveryWaitPointsEnough
      displayName: Recovery - Enough Points for the Waiting Period
      properties:
        valueProvider:
          type: BooleanFromMapValueProvider
          id: recoveryWaitPointsEnoughValue
          displayName: Recovery - Enough Points for the Waiting Period (value "waitAvailable")
          properties:
            key: waitAvailable
            provideFalseIfEmpty: 'true'
            valueMaps:
            - pluginList:
              - ref: recoveryTotalResult
    - type: LogicalNotFlowCondition
      id: recoveryNotWaiting
      displayName: Recovery - Not Waiting
      properties:
        condition:
          ref: recoveryWaitPending""" % KNOWN_BROWSER_POINTS

WAIT_PENDING_DEF = """type: BooleanCondition
id: recoveryWaitPending
displayName: Recovery - Waiting Period Running
properties:
  valueProvider:
    type: BooleanFromMapValueProvider
    id: recoveryWaitPendingValue
    displayName: Recovery - Waiting Period Running (value "pending")
    properties:
      key: pending
      provideFalseIfEmpty: 'true'
      valueMaps:
      - pluginList:
        - ref: recoveryRestoreResult"""


def bool_restore(id_, disp, key):
    return f"""type: BooleanCondition
id: {id_}
displayName: {disp}
properties:
  valueProvider:
    type: BooleanFromMapValueProvider
    id: {id_}Value
    displayName: {disp} (value "{key}")
    properties:
      key: {key}
      provideFalseIfEmpty: 'true'
      valueMaps:
      - pluginList:
        - ref: recoveryRestoreResult"""


def setctx_state(id_, disp, values, skip=None, blk=None):
    """Set Context Data recovery_state / recovery_wait_until: values = {name: ('map', key) | ('static', '')}"""
    items = []
    for name, (kind, val) in values.items():
        cid = ''.join(x.title() for x in name.split('_'))
        if kind == 'map':
            vp = f"""type: StringFromMapValueProvider
id: {id_}{cid}Value
displayName: {disp} - Value {name}
properties:
  key: {val}
  valueMaps:
  - pluginList:
    - ref: recoveryWaitStartResult"""
        else:
            vp = f"""type: StringStaticValueProvider
id: {id_}{cid}Value
displayName: {disp} - Value {name} empty
properties:
  value: ''"""
        items.append(f"""- type: StringNonInteractiveUserDataItemDefinition
  id: {id_}{cid}
  displayName: {disp} - {name}
  properties:
    contextDataItemNameConfig:
      ref: ctxDataItem{cid}Name
    valueProviderConfig:
{blk(vp, 6)}""")
    st = f"""- type: NonInteractiveSetContextDataStep
  id: {id_}
  displayName: {disp}
  properties:
    userDataItems:
    - pluginList:
{blk(chr(10).join(items), 6)}"""
    if skip:
        st += "\n    skipCondition:\n" + blk(skip, 6)
    return st


def clear_state(id_, disp, skip=None, blk=None):
    return setctx_state(id_, disp, {'recovery_state': ('static', ''), 'recovery_wait_until': ('static', '')}, skip, blk)


def wait_body(r, method_keys, output, blk, lua_inputs):
    """round r: start the waiting period (save state, email, message, end of the flow)"""
    start_ns = ("ref: recoveryWaitStartNamespace" if r > 1 else """type: ScriptNamespace
id: recoveryWaitStartNamespace
displayName: Script Namespace recovery-wait-start
properties:
  identifier: recovery-wait-start""")
    start = f"""- type: ScriptableStep
  id: recoveryWaitStartR{r}
  displayName: Recovery Round {r} - Waiting Period - Start (state to save)
  properties:
    inputs:
    - pluginList:
{blk(lua_inputs, 6)}
    namespace:
{blk(start_ns, 6)}
    outputs:
    - pluginMap:
{blk(output('state', f'recoveryWaitOutStateR{r}', 'S'), 8)}
{blk(output('waitUntil', f'recoveryWaitOutUntilR{r}', 'S'), 8)}
{blk(output('minutes', f'recoveryWaitOutMinutesR{r}', 'S'), 8)}
    script: |
{blk(start_script(method_keys, r), 6)}"""
    store = setctx_state(f'recoveryWaitStoreR{r}', f'Recovery Round {r} - Waiting Period - State Saved',
                         {'recovery_state': ('map', 'state'), 'recovery_wait_until': ('map', 'waitUntil')}, blk=blk)
    mail = f"""- type: EmailNotificationStep
  id: recoveryWaitMailR{r}
  displayName: Recovery Round {r} - Waiting Period - Email to the User
  properties:
    emailService:
      ref: emailService
    recipientAddressProvider:
      ref: userEmailProvider
    subjectResourceKey: custom.recovery.email.wait.subject
    bodyResourceKey: custom.recovery.email.wait.body
    valueMapProviders:
    - pluginList:
      - ref: userContextDataMap
      - ref: recoveryWaitStartResult"""
    message = f"""- type: AcknowledgeMessageStep
  id: recoveryWaitStartedR{r}
  displayName: Recovery Round {r} - Waiting Period - Come Back Later (message)
  properties:
    messageId: recovery-wait-started
    customResponseAttributes:
    - pluginList:
      - ref: recoveryWaitStartResult"""
    abort = f"""- type: AbortStep
  id: recoveryWaitAbortR{r}
  displayName: Recovery Round {r} - Waiting Period - End of the Flow
  properties:
    errorCode: RECOVERY_WAITING"""
    return [start, store, mail, message, abort]


WAIT_START_RESULT_DEF = """type: ScriptExecutionResultValueMapProvider
id: recoveryWaitStartResult
displayName: Recovery - Waiting Period Started (state, end, minutes)
properties:
  namespaceConfig:
    ref: recoveryWaitStartNamespace"""


def pending_option(r, blk):
    cond = WAIT_PENDING_DEF if r == 1 else "ref: recoveryWaitPending"
    return f"""- type: SelectionOption
  id: recoveryWaitPendingOptionR{r}
  displayName: Recovery Round {r} - Waiting Period Running Option (come back later)
  properties:
    condition:
{blk(cond, 6)}
    name: RECOVERY_WAIT_PENDING
    steps:
    - pluginList:
      - type: AcknowledgeMessageStep
        id: recoveryWaitPendingMessageR{r}
        displayName: Recovery Round {r} - Waiting Period Running (message)
        properties:
          messageId: recovery-wait-pending
          customResponseAttributes:
          - pluginList:
            - ref: recoveryRestoreResult
      - type: AbortStep
        id: recoveryWaitPendingAbortR{r}
        displayName: Recovery Round {r} - Waiting Period Running - End of the Flow
        properties:
          errorCode: RECOVERY_WAITING"""


def restore_step(method_keys, rounds, output, blk):
    outs = [output('resumed', 'recoveryRestoreOutResumed', 'B'), output('pending', 'recoveryRestoreOutPending', 'B'),
            output('expired', 'recoveryRestoreOutExpired', 'B'), output('minutesLeft', 'recoveryRestoreOutMinutes', 'S'),
            output('untilIso', 'recoveryRestoreOutUntilIso', 'S'), output('untilUtc', 'recoveryRestoreOutUntilUtc', 'S')]
    outs += [output(f'skipR{r}', f'recoveryRestoreOutSkipR{r}', 'B') for r in range(1, rounds + 1)]
    for k in method_keys:
        for suffix, typ in (('Done', 'B'), ('Points', 'S')):
            outs.append(output(k + suffix, f'recoveryRestoreOut{k[0].upper()}{k[1:]}{suffix}', typ).replace("required: 'true'", "required: 'false'"))
    return f"""- type: ScriptableStep
  id: recoveryRestoreStep
  displayName: Recovery - Continue a Saved Recovery (waiting period)
  properties:
    inputs:
    - pluginList:
      - ref: userIdentityInfoMap
      - ref: userContextDataMap
    namespace:
      type: ScriptNamespace
      id: recoveryRestoreNamespace
      displayName: Script Namespace recovery-restore
      properties:
        identifier: recovery-restore
    outputs:
    - pluginMap:
{blk(chr(10).join(outs), 8)}
    script: |
{blk(restore_script(method_keys, rounds), 6)}"""


LOGIN_CANCEL_STEP_ID = 'recoveryCancelByLogin'
