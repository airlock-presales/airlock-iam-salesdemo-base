#!/usr/bin/env python3
"""Generates the account recovery of the IAM configuration (iam/iam-config.yaml): points-based recovery
flow (target application recovery), alternate email address (context data, Adminapp field, self-service),
administrator self-service "Confirm account recovery", the related context data items.

Usage: tools/iam-recovery/generate.py iam/iam-config.yaml   (in place; validate with check_config.py)

Repeatable: everything a previous run generated is removed first (strip), then rebuilt - change the
methods, points, rounds or texts here (METHODS, ROUNDS, THRESHOLD, Lua in lua_lib.py) and run it again on
base/iam/iam-config.yaml, then copy the result to the instances. Texts (design kit, loginapp-texts) and the
database columns (init_db) are maintained separately. See README.md.
"""
import sys,re
import os
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from yamlsteps import step_range, ind
import waitdefs as W
import iddefs as I
from smsdefs import EXTRA_DEFS, SMS_DEFS, mtan_step, define_first, MTAN_CHANGE_FLOW, MTAN_CHANGE_UI, MTAN_CHANGE_PORTAL, MTAN_CTX_ITEM, MTAN_PROFILE_ITEM
EXTRA_DEFS['recoveryWaitAvailable']=W.WAIT_AVAILABLE_DEF
EXTRA_DEFS['hasIdDocument']=I.HAS_ID_DOCUMENT_DEF

def y(text,n): return [(' '*n+l) if l.strip() else l for l in text.strip('\n').split('\n')]
def blk(text,n): return '\n'.join(y(text,n))

ROUNDS=6
from lua_lib import LUA_LIB
CONFIRM_MINUTES=15
THRESHOLD=25
METHODS=[  # key, option name, points, condition extra (None = always), dummy
 ('EmailAlt','RECOVERY_EMAIL_ALT',8,'hasEmailAlt',False),
 ('Mtan','RECOVERY_MTAN',1,'hasMtanNumber',False),
 ('ContactCode','RECOVERY_CONTACT_CODE',12,None,False),
 ('ContactConfirm','RECOVERY_CONTACT_CONFIRM',20,None,False),
 ('Wait','RECOVERY_WAIT',10,'recoveryWaitAvailable',False),
 ('IdDocument','RECOVERY_ID_DOCUMENT',25,'hasIdDocument',False),
 ('Iban','RECOVERY_IBAN',30,None,True),
 ('Atm','RECOVERY_ATM',50,None,True),
 ('Statement','RECOVERY_STATEMENT',24,None,True),
]
def ns(k): return 'recovery-'+re.sub(r'(?<!^)([A-Z])',r'-\1',k).lower()

def bool_from(id_,disp,key,mapref):
    maps='\n'.join('        - ref: '+m for m in (mapref if isinstance(mapref,list) else [mapref]))
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
{maps}"""

def not_(id_,disp,cond):  # cond: lines of an inline condition or "ref: x"
    return f"""type: LogicalNotFlowCondition
id: {id_}
displayName: {disp}
properties:
  condition:
{blk(cond,4)}"""

def output(key,id_,typ):
    return f"""{key}:
  type: ScriptExpectedOutputType
  id: {id_}
  displayName: Recovery Output "{key}" ({id_})
  properties:
    outputType:
      ref: {'selfRegLookupOutputTypeString' if typ=='S' else 'selfRegLookupOutputTypeBoolean'}
    required: 'true'"""

def points_script(k,pts,r,dummy):
    return f"""- type: ScriptableStep
  id: recovery{k}PointsR{r}
  displayName: Recovery Round {r} - {k} Done ({0 if dummy else pts} points)
  properties:
    namespace:
      ref: recovery{k}Namespace
    outputs:
    - pluginMap:
{blk(output(k[0].lower()+k[1:]+'Done','recovery'+k+'OutDoneR'+str(r),'B'),8)}
{blk(output(k[0].lower()+k[1:]+'Points','recovery'+k+'OutPointsR'+str(r),'S'),8)}
    script: |
      function iam_on_step_init ()
          return {{ {k[0].lower()+k[1:]}Done = true, {k[0].lower()+k[1:]}Points = "{0 if dummy else pts}" }}
      end"""

SUM_SCRIPT='''-- account recovery: sum of the points of all confirmations done so far
local THRESHOLD = %d
function iam_on_step_init ()
    local total = 0
    for _, key in ipairs({ "knownBrowserPoints", %s }) do
        total = total + (tonumber(iam.input_map[key]) or 0)
    end
    -- the waiting period is offered only with more points than the known browser alone gives
    return { total = tostring(total), threshold = tostring(THRESHOLD), reached = total >= THRESHOLD,
        waitAvailable = total > %d }
end''' % (THRESHOLD, ', '.join('"%s%sPoints"' % (k[0].lower(),k[1:]) for k,*_ in METHODS), W.KNOWN_BROWSER_POINTS)

def sum_step(id_,disp,first=False):
    inputs=["- ref: recoveryRestoreResult","- ref: recoveryKnownBrowserResult"]+[f"- ref: recovery{k}Result" for k,*_ in METHODS]
    outs=[output('total',id_+'OutTotal','S'),output('threshold',id_+'OutThreshold','S'),output('reached',id_+'OutReached','B'),
          output('waitAvailable',id_+'OutWaitAvailable','B')]
    return f"""- type: ScriptableStep
  id: {id_}
  displayName: {disp}
  properties:
    inputs:
    - pluginList:
{blk(chr(10).join(inputs),6)}
    namespace:
      ref: recoveryTotalNamespace
    outputs:
    - pluginMap:
{blk(chr(10).join(outs),8)}
    script: |
{blk(SUM_SCRIPT,6)}"""

def msg(id_,disp,mid,skip=None,attrs=()):
    s=f"""- type: AcknowledgeMessageStep
  id: {id_}
  displayName: {disp}
  properties:
    messageId: {mid}
    # text: design kit key authentication.acknowledgement.message.{mid}.content ({{{{ customAttributes.total }}}} / threshold)
    customResponseAttributes:
    - pluginList:
      - ref: recoveryTotalResult"""+''.join('\n      - ref: '+a for a in attrs)
    if skip: s+=f"\n    skipCondition:\n{blk(skip,6)}"
    return s

# ------------------------------------------------------------------ plugin definitions used everywhere
NAMESPACES='\n'.join(f"""- type: ScriptExecutionResultValueMapProvider
  id: recovery{k}Result
  displayName: Recovery {k} Result
  properties:
    namespaceConfig:
      type: ScriptNamespace
      id: recovery{k}Namespace
      displayName: Script Namespace {ns(k)}
      properties:
        identifier: {ns(k)}""" for k in ['KnownBrowser']+[m[0] for m in METHODS])



DELETE_SCRIPT='''-- account recovery: delete all second factors (Airlock 2FA account, passkeys, OATH OTP tokens) through
-- the Adminapp REST API - the email OTP opt-in is reset by the next step, a new factor is registered after.
local curl = require "cURL"
local BASE = "http://localhost:8080/auth-admin/rest"

local function urlencode (s)
    return (s:gsub("[^%w%-%._~]", function (c) return string.format("%%%02X", string.byte(c)) end))
end

local function call (method, path, body, accepted)
    local response = ""
    local options = {
        url = BASE .. path,
        customrequest = method,
        httpheader = { "Accept: application/vnd.api+json", "X-Same-Domain: 1" },
        username = "selfreg-lookup",
        password = iam.secrets:get("PASSWORD"),
        writefunction = function (chunk) response = response .. chunk end,
        [curl.OPT_TIMEOUT] = 10
    }
    -- Content-Type only with a body (DELETE with a Content-Type is answered with 415)
    if body then
        options.postfields = iam.cjson.encode(body)
        table.insert(options.httpheader, "Content-Type: application/vnd.api+json")
    end
    local request = curl.easy(options)
    local ok = pcall(request.perform, request)
    local status = ok and request:getinfo(curl.INFO_RESPONSE_CODE) or 0
    request:close()
    for _, code in ipairs(accepted) do
        if status == code then return (response ~= "" and iam.cjson.decode(response)) or {} end
    end
    error("Recovery: " .. method .. " " .. path .. " failed (HTTP " .. status .. ")")
end

function iam_on_step_init ()
    local user = urlencode(iam.input_map["user-id"])
    local deleted = 0
    call("DELETE", "/users/" .. user .. "/tokens/airlock-2fa", nil, { 200, 204, 404 })
    for _, c in ipairs(call("GET", "/users/" .. user .. "/tokens/fido/credentials", nil, { 200 }).data or {}) do
        call("DELETE", "/users/" .. user .. "/tokens/fido/credentials/" .. urlencode(c.id), nil, { 200, 204, 404 })
        deleted = deleted + 1
    end
    for _, t in ipairs(call("GET", "/users/" .. user .. "/tokens/oath/totp", nil, { 200 }).data or {}) do
        call("DELETE", "/users/" .. user .. "/tokens/oath/totp/" .. urlencode(t.id), nil, { 200, 204, 404 })
        deleted = deleted + 1
    end
    iam.log:info("Recovery: second factors of " .. iam.input_map["user-id"] .. " deleted (Airlock 2FA account, "
        .. deleted .. " passkeys/OATH tokens, email OTP disabled)")
    return { deleted = tostring(deleted) }
end'''

def lua(script): return LUA_LIB+'\n'+script

def ctx_item(id_,name,disp):
    return f"""- type: StringContextDataItem
  id: {id_}
  displayName: {disp}
  properties:
    contextDataName:
      type: StringContextDataItemName
      id: {id_}Name
      displayName: String Context Data '{name}'
      properties:
        contextDataName: {name}"""

def step_id(id_,value,disp):
    """stepId property (as 'extra' of lua_step)"""
    return f"""
    stepId:
      type: StepId
      id: {id_}
      displayName: {disp} Step ID "{value}"
      properties:
        id: {value}"""

def lua_step(id_,disp,nsref,outs,script,inputs=('userIdentityInfoMap',),extra=''):
    inp=chr(10).join('- ref: '+x if not x.startswith('- ') else x for x in inputs)
    return f"""- type: ScriptableStep
  id: {id_}
  displayName: {disp}
  properties:
    inputs:
    - pluginList:
{blk(inp,6)}
    inputSecrets:
    - pluginList:
      - ref: selfRegLookupPasswordSecret
    namespace:
{blk(nsref,6)}
    outputs:
    - pluginMap:
{blk(chr(10).join(outs),8)}{extra}
    script: |
{blk(lua(script),6)}"""

CODE_SEND = r"""-- account recovery: code via contact - new code for the contacts of the user (not for
-- registration-orphan users: nobody is asked, the code never arrives)
function iam_on_step_init ()
    local user = iam.input_map["user-id"]
    local code = new_code(6)
    local name = ((iam.input_map["givenname"] or "") .. " " .. (iam.input_map["surname"] or "")):gsub("^%s+", ""):gsub("%s+$", "")
    -- contacts as outputs contact1..5, the next steps send the emails
    return contact_outputs(user, { code = code, name = name, username = user })
end"""

CODE_VERIFY = r"""-- account recovery: code via contact - compare the entered code (edited context data recovery_code)
local POINTS = 12
function iam_on_step_init ()
    local entered = (iam.input_map["recovery_code"] or ""):gsub("%s", "")
    local ok = entered ~= "" and entered == iam.input_map["code"]
    iam.log:info("Recovery: code via contact for " .. tostring(iam.input_map["user-id"]) .. (ok and " correct" or " wrong"))
    return { contactCodeDone = ok, contactCodePoints = ok and tostring(POINTS) or "0", contactCodeOk = ok }
end"""

CONFIRM_REQUEST = r"""-- account recovery: confirmation by a contact - new request (code, expiry) and ask all contacts by email;
-- the next step stores it with the user (context data recovery_request, recovery_request_until)
local MINUTES = %d
function iam_on_step_init ()
    local user = iam.input_map["user-id"]
    local code = new_code(8)
    local untilTime = tostring(os.time() + MINUTES * 60)
    local name = ((iam.input_map["givenname"] or "") .. " " .. (iam.input_map["surname"] or "")):gsub("^%%s+", ""):gsub("%%s+$", "")
    -- stored with the user by the next step (Set Context Data); contacts as outputs contact1..5, the
    -- email notification steps after it send the emails
    return contact_outputs(user, { requested = true, requestCode = code, requestUntil = untilTime,
        code = code, name = name, username = user, minutes = tostring(MINUTES) })
end""" % CONFIRM_MINUTES

CONFIRM_CHECK = r"""-- account recovery: confirmation by a contact - wait up to 20 seconds for the confirmation (the browser
-- request waits meanwhile: route timeout 35 s, IAM script limit 30 s); then "not confirmed yet" / "check again"
-- (context data recovery_confirmed_by, set by the self-service "Confirm account recovery")
local socket = require "socket"
local POINTS = 20
local WAIT = 20
function iam_on_step_init ()
    local user = iam.input_map["user-id"]
    local deadline = socket.gettime() + WAIT
    repeat
        local c = (call("GET", "/users/" .. urlencode(user) .. "/context-data", nil, { 200 }).data or {}).attributes or {}
        if type(c.recovery_confirmed_by) == "string" and c.recovery_confirmed_by ~= "" then
            iam.log:info("Recovery: " .. user .. " confirmed by " .. c.recovery_confirmed_by)
            return { contactConfirmDone = true, contactConfirmPoints = tostring(POINTS) }
        end
        socket.sleep(2)
    until socket.gettime() >= deadline
    return { contactConfirmDone = false, contactConfirmPoints = "0" }
end"""

CONFIRM_SELFSERVICE = r"""-- self-service "Confirm account recovery": an administrator enters the code of a recovery request;
-- allowed if the administrator is one of the contacts of that user and the request is not expired
function iam_on_step_init ()
    local admin = iam.input_map["user-id"]
    local code = (iam.input_map["recovery_code"] or ""):gsub("%s", "")
    if code == "" then return { result = "not-found" } end
    local list = call("GET", "/users?page%5Blimit%5D=2&filter=" .. urlencode("recovery_request==" .. code), nil, { 200 }).data or {}
    if #list ~= 1 then
        iam.log:info("Recovery confirmation by " .. admin .. ": no request with this code")
        return { result = "not-found" }
    end
    local user = list[1].id
    local c = ((list[1].attributes or {}).contextData) or {}
    if (tonumber(c.recovery_request_until) or 0) < os.time() then
        iam.log:info("Recovery confirmation by " .. admin .. " for " .. user .. ": request expired")
        return { result = "expired" }
    end
    local contacts = contacts_of(user)
    for _, k in ipairs(contacts) do
        if k.username == admin then
            set_context(user, { recovery_confirmed_by = admin })
            iam.log:info("Recovery confirmation: " .. user .. " confirmed by " .. admin)
            return { result = "confirmed" }
        end
    end
    iam.log:warn("Recovery confirmation by " .. admin .. " for " .. user .. ": not a contact of this user")
    return { result = "not-allowed" }
end"""

def mails(prefix,kind,r,resultref):
    """email notification steps to the contacts contact1..contact5 of a script result (skipped if empty)"""
    out=[]
    for i in range(1,6):
        out.append(f"""- type: EmailNotificationStep
  id: {prefix}Mail{i}R{r}
  displayName: Recovery Round {r} - {kind.title()} Email to Contact {i}
  properties:
    emailService:
      ref: emailService
    recipientAddressProvider:
      type: StringFromMapValueProvider
      id: {prefix}Contact{i}R{r}
      displayName: Recovery Round {r} - {kind.title()} Contact {i} (email)
      properties:
        key: contact{i}
        valueMaps:
        - pluginList:
          - ref: {resultref}
    skipCondition:
      type: LogicalOrFlowCondition
      id: {prefix}MailSkip{i}R{r}
      displayName: Recovery Round {r} - {kind.title()} Email {i} Skipped (no address, or SMS instead)
      properties:
        conditions:
        - pluginList:
          - type: LogicalNotFlowCondition
            id: {prefix}NoContact{i}R{r}
            displayName: Recovery Round {r} - {kind.title()} No Contact {i}
            properties:
              condition:
                type: StringRegexCondition
                id: {prefix}HasContact{i}R{r}
                displayName: Recovery Round {r} - {kind.title()} Has Contact {i}
                properties:
                  regexPattern: .+
                  valueProvider:
                    ref: {prefix}Contact{i}R{r}
          - type: LogicalAndFlowCondition
            id: {prefix}SmsInstead{i}R{r}
            displayName: Recovery Round {r} - {kind.title()} SMS to Contact {i} Instead
            properties:
              conditions:
              - pluginList:
                - ref: smsEnabled
                - type: StringRegexCondition
                  id: {prefix}HasPhone{i}R{r}
                  displayName: Recovery Round {r} - {kind.title()} Contact {i} Has Mobile Number
                  properties:
                    regexPattern: .+
                    valueProvider:
                      type: StringFromMapValueProvider
                      id: {prefix}Phone{i}R{r}
                      displayName: Recovery Round {r} - {kind.title()} Contact {i} (mobile number)
                      properties:
                        key: phone{i}
                        valueMaps:
                        - pluginList:
                          - ref: {resultref}
    subjectResourceKey: custom.recovery.contact.{kind}.subject
    bodyResourceKey: custom.recovery.contact.{kind}.body
    valueMapProviders:
    - pluginList:
      - ref: {resultref}""")
    return out

def code_item(id_,disp):
    return f"""- type: StringContextDataItemDefinition
  id: {id_}
  displayName: {disp}
  properties:
    contextDataName:
      ref: ctxDataItemRecoveryCodeName
    inputPurpose: one-time-code"""

def contact_code_body(r):
    send=lua_step(f"recoveryContactCodeSendR{r}",f"Recovery Round {r} - Code via Contact - Send",
        "ref: recoveryContactCodeSendNamespace" if r>1 else """type: ScriptNamespace
id: recoveryContactCodeSendNamespace
displayName: Script Namespace recovery-contact-code-send
properties:
  identifier: recovery-contact-code-send""",
        [output('code',f'recoveryContactCodeSendOutCodeR{r}','S'),output('name',f'recoveryContactCodeSendOutNameR{r}','S'),
         output('username',f'recoveryContactCodeSendOutUserR{r}','S')]+[output(f'contact{i}',f'recoveryContactCodeSendOutContact{i}R{r}','S') for i in range(1,6)]
         +[output(f'phone{i}',f'recoveryContactCodeSendOutPhone{i}R{r}','S') for i in range(1,6)],CODE_SEND,inputs=('userIdentityInfoMap','userContextDataMap'),
        extra=step_id(f'recoveryContactCodeSendStepIdR{r}',f'recovery-code-send-{r}',f'Recovery Round {r} Code Send'))
    verify_inputs=('- type: UserDataEditValueMapProvider\n  id: recoveryEditedCodeMap\n  displayName: Recovery - Entered Code (edited context data)' if r==1 else 'recoveryEditedCodeMap',
                   'userIdentityInfoMap',
                   '- type: ScriptExecutionResultValueMapProvider\n  id: recoveryContactCodeSendResult\n  displayName: Recovery Code via Contact - Sent Code\n  properties:\n    namespaceConfig:\n      ref: recoveryContactCodeSendNamespace' if r==1 else 'recoveryContactCodeSendResult')
    verify=f"""- type: ScriptableStep
  id: recoveryContactCodeVerifyR{r}
  displayName: Recovery Round {r} - Code via Contact - Verify (12 points)
  properties:
    inputs:
    - pluginList:
{blk(chr(10).join(x if x.startswith('- ') else '- ref: '+x for x in verify_inputs),6)}
    namespace:
      ref: recoveryContactCodeNamespace
    outputs:
    - pluginMap:
{blk(output('contactCodeDone',f'recoveryContactCodeOutDoneR{r}','B'),8)}
{blk(output('contactCodePoints',f'recoveryContactCodeOutPointsR{r}','S'),8)}
{blk(output('contactCodeOk',f'recoveryContactCodeOutOkR{r}','B'),8)}
    script: |
{blk(CODE_VERIFY,6)}"""
    ok_cond=bool_from('recoveryContactCodeOk','Recovery - Code via Contact Correct','contactCodeOk','recoveryContactCodeResult') if r==1 else 'ref: recoveryContactCodeOk'
    return [send]+mails('recoveryContactCode','code',r,'recoveryContactCodeSendResult')+[
      f"""- type: AcknowledgeMessageStep
  id: recoveryContactCodeSentR{r}
  displayName: Recovery Round {r} - Code via Contact - Ask Your Administrator
  properties:
    messageId: recovery-contact-code""",
      f"""- type: UserDataEditStep
  id: recoveryContactCodeEntryR{r}
  displayName: Recovery Round {r} - Code via Contact - Enter Code
  properties:
    stepId:
      type: StepId
      id: recoveryContactCodeEntryStepIdR{r}
      displayName: Recovery Round {r} Code Entry Step ID "recovery-code-{r}"
      properties:
        id: recovery-code-{r}
    userDataItems:
    - pluginList:
{blk(code_item('recoveryCodeItemR'+str(r),'Recovery Round '+str(r)+' - Code via Contact (input)'),6)}""",
      verify,
      sum_step(f"recoveryTotalContactCodeR{r}",f"Recovery Round {r} - Points After Code via Contact"),
      f"""- type: AcknowledgeMessageStep
  id: recoveryContactCodeWrongMessageR{r}
  displayName: Recovery Round {r} - Code via Contact - Wrong Code
  properties:
    messageId: recovery-code-wrong
    skipCondition:
{blk(ok_cond,6)}"""]

def contact_confirm_body(r):
    req=lua_step(f"recoveryContactConfirmRequestR{r}",f"Recovery Round {r} - Confirmation by Contact - Request",
        "ref: recoveryContactConfirmRequestNamespace" if r>1 else """type: ScriptNamespace
id: recoveryContactConfirmRequestNamespace
displayName: Script Namespace recovery-contact-confirm-request
properties:
  identifier: recovery-contact-confirm-request""",
        [output('requested',f'recoveryContactConfirmOutRequestedR{r}','B'),
         output('requestCode',f'recoveryContactConfirmOutCodeR{r}','S'),
         output('requestUntil',f'recoveryContactConfirmOutUntilR{r}','S'),
         output('code',f'recoveryContactConfirmOutMailCodeR{r}','S'),output('name',f'recoveryContactConfirmOutNameR{r}','S'),
         output('username',f'recoveryContactConfirmOutUserR{r}','S'),output('minutes',f'recoveryContactConfirmOutMinutesR{r}','S')]
         +[output(f'contact{i}',f'recoveryContactConfirmOutContact{i}R{r}','S') for i in range(1,6)]
         +[output(f'phone{i}',f'recoveryContactConfirmOutPhone{i}R{r}','S') for i in range(1,6)],CONFIRM_REQUEST,inputs=('userIdentityInfoMap','userContextDataMap'),
        extra=step_id(f'recoveryContactConfirmRequestStepIdR{r}',f'recovery-confirm-request-{r}',f'Recovery Round {r} Confirmation Request'))
    check=lua_step(f"recoveryContactConfirmCheckR{r}",f"Recovery Round {r} - Confirmation by Contact - Check (waits up to 20 s, 20 points)",
        "ref: recoveryContactConfirmNamespace",
        [output('contactConfirmDone',f'recoveryContactConfirmOutDoneR{r}','B'),output('contactConfirmPoints',f'recoveryContactConfirmOutPointsR{r}','S')],
        CONFIRM_CHECK,
        extra=f"""
    stepId:
      type: StepId
      id: recoveryContactConfirmCheckStepIdR{r}
      displayName: Recovery Round {r} Confirmation Check Step ID "recovery-confirm-check-{r}"
      properties:
        id: recovery-confirm-check-{r}""")
    done_cond=bool_from('recoveryContactConfirmDoneNow','Recovery - Confirmed by Contact','contactConfirmDone','recoveryContactConfirmResult') if r==1 else 'ref: recoveryContactConfirmDoneNow'
    def setctx(id_,disp,items,skip=None):
        it=[]
        for name,(kind,val) in items.items():
            cid=''.join(x.title() for x in name.split('_'))
            if kind=='map':
                src='ref: recoveryContactConfirmRequestResult' if (r>1 or 'Store' not in id_ or it) else 'PLACEHOLDER_REQ'
                vp=("type: StringFromMapValueProvider\nid: %s%sValue\ndisplayName: %s - Value %s\nproperties:\n  key: %s\n  valueMaps:\n  - pluginList:\n    - %s"
                    % (id_,cid,disp,name,val,src))
            else:
                vp=("type: StringStaticValueProvider\nid: %s%sValue\ndisplayName: %s - Value %s empty\nproperties:\n  value: ''"
                    % (id_,cid,disp,name))
            it.append("- type: StringNonInteractiveUserDataItemDefinition\n  id: %s%s\n  displayName: %s - %s\n  properties:\n    contextDataItemNameConfig:\n      ref: ctxDataItem%sName\n    valueProviderConfig:\n%s"
                      % (id_,cid,disp,name,cid,blk(vp,6)))
        st=("- type: NonInteractiveSetContextDataStep\n  id: %s\n  displayName: %s\n  properties:\n    userDataItems:\n    - pluginList:\n%s"
            % (id_,disp,blk('\n'.join(it),6)))
        if skip: st+="\n    skipCondition:\n"+blk(skip,6)
        return st
    store=setctx('recoveryContactConfirmStoreR%d'%r,'Recovery Round %d - Confirmation Request Stored'%r,
        {'recovery_request':('map','requestCode'),'recovery_request_until':('map','requestUntil'),'recovery_confirmed_by':('static','')})
    if r==1:
        store=store.replace('- PLACEHOLDER_REQ',"- type: ScriptExecutionResultValueMapProvider\n  id: recoveryContactConfirmRequestResult\n  displayName: Recovery Confirmation Request (code, expiry)\n  properties:\n    namespaceConfig:\n      ref: recoveryContactConfirmRequestNamespace".replace('\n','\n'+' '*(store.split('- PLACEHOLDER_REQ')[0].split('\n')[-1].__len__())),1)
    clear=setctx('recoveryContactConfirmClearR%d'%r,'Recovery Round %d - Confirmation Request Cleared'%r,
        {'recovery_request':('static',''),'recovery_request_until':('static',''),'recovery_confirmed_by':('static','')},
        skip=not_('recoveryContactConfirmNotDoneR%d'%r,'Recovery Round %d - Not Confirmed (keep request)'%r,'ref: recoveryContactConfirmDoneNow'))
    return [req, store]+mails('recoveryContactConfirm','confirm',r,'recoveryContactConfirmRequestResult')+[
      f"""- type: AcknowledgeMessageStep
  id: recoveryContactConfirmWaitR{r}
  displayName: Recovery Round {r} - Confirmation by Contact - Ask Your Administrator
  properties:
    messageId: recovery-contact-confirm""",
      check,
      f"""- type: AcknowledgeMessageStep
  id: recoveryContactConfirmPendingR{r}
  displayName: Recovery Round {r} - Confirmation by Contact - Not Confirmed Yet (check again or give up)
  properties:
    messageId: recovery-contact-pending
    stepId:
      type: StepId
      id: recoveryContactConfirmPendingStepIdR{r}
      displayName: Recovery Round {r} Confirmation Pending Step ID "recovery-confirm-pending-{r}"
      properties:
        id: recovery-confirm-pending-{r}
    interactiveGotoTargets:
    - pluginList:
      - type: InteractiveGotoTarget
        id: recoveryContactConfirmAgainR{r}
        displayName: Recovery Round {r} - Check Confirmation Again
        properties:
          targetStepId:
            ref: recoveryContactConfirmCheckStepIdR{r}
    skipCondition:
{blk(done_cond,6)}""",
      clear,
      sum_step(f"recoveryTotalContactConfirmR{r}",f"Recovery Round {r} - Points After Confirmation by Contact")]


# ------------------------------------------------------------------ strip (makes the generator repeatable)
GENERATED_IDS=['recoveryConfirmedByLabel','recoveryRequestLabel','recoveryRequestUntilLabel','ctxDataItemEmailAlt','ctxDataItemRecoveryCode','ctxDataItemRecoveryRequest','ctxDataItemRecoveryRequestUntil',
               'ctxDataItemRecoveryConfirmedBy','emailAltLabel','emailAltChangeFlow','recoveryConfirmFlow','emailAltChangeUi',
               'recoveryConfirmUi','portalTarget-email-alt-change','portalTarget-recovery-confirm',
               'ctxDataItemMtanNumber',*I.GENERATED,'ctxDataItemRecoveryState','ctxDataItemRecoveryWaitUntil',W.LOGIN_CANCEL_STEP_ID,'mtanNumberLabel','mtanNumberChangeFlow','mtanNumberChangeUi','portalTarget-mtan-number-change']
ORIGINAL_EMAIL_STEP = r"""- type: EmailOtpAuthenticationStep
  id: recoveryEmailOtpStep
  displayName: Email OTP Authentication Step (recovery, no opt-in required)
  properties:
    emailMessageProvider:
      ref: emailOtpAuthMessage
    emailService:
      ref: emailService
    maxResends: '1'
    maxRetries: '2'
    messageTemplateIsHtml: 'false'
    recipientAddress:
      ref: userEmailProvider
    tagsOnSuccess:
    - pluginList:
      - ref: emailOtpVerified
      - type: TagConfigImpl
        id: accountRecovery
        displayName: Account Recovery Tag
        properties:
          name: ACCOUNT_RECOVERY"""

def strip(p):
    """remove everything a previous run generated: the configuration is then as before the generator"""
    L=open(p).read().split('\n')
    anchor=[x for x in ('recoveryUserStateStep','recoveryNoFactorMark') if any(l.strip()==f'id: {x}' for l in L)]
    if not anchor:
        return False
    for pid in GENERATED_IDS:
        if not any(l.strip()==f'id: {pid}' for l in L): continue   # e.g. added by a newer version
        i,j=step_range(L,pid); del L[i:j]
    # recovery flow: from the user state step to the end of the step list -> the original email OTP step
    a,_=step_range(L,anchor[0]); n=ind(L[a])
    e=a
    while e<len(L) and (L[e].strip()=='' or ind(L[e])>=n): e+=1
    L[a:e]=y(ORIGINAL_EMAIL_STEP,n)
    t='\n'.join(L).replace("displayName: Account Recovery Flow (password, email code, confirmations with points, new second factor)",
                         "displayName: Account Recovery Flow (password and email code)")
    open(p,'w').write(t)
    return True

def build(p):
    L=open(p).read().split('\n')
    # ---- 1. user store: context data email_alt
    i,j=step_range(L,'ctxDataItemResponsibleAdmin'); n=ind(L[i])
    L[j:j]=y("\n".join([ctx_item('ctxDataItemRecoveryCode','recovery_code',"Context Data Item 'recovery_code' (recovery code input, never stored)"),
                         ctx_item('ctxDataItemRecoveryRequest','recovery_request',"Context Data Item 'recovery_request' (open recovery confirmation)"),
                         ctx_item('ctxDataItemRecoveryRequestUntil','recovery_request_until',"Context Data Item 'recovery_request_until' (expiry, epoch seconds)"),
                         ctx_item('ctxDataItemRecoveryConfirmedBy','recovery_confirmed_by',"Context Data Item 'recovery_confirmed_by' (administrator who confirmed)"),
                         ctx_item('ctxDataItemRecoveryState','recovery_state',"Context Data Item 'recovery_state' (saved recovery - round and points, JSON)"),
                         ctx_item('ctxDataItemRecoveryWaitUntil','recovery_wait_until',"Context Data Item 'recovery_wait_until' (end of the waiting period, epoch seconds)")]),n)
    L[j:j]=y("""- type: StringContextDataItem
  id: ctxDataItemEmailAlt
  displayName: Context Data Item 'email_alt'
  comment: Alternate email address of the user (account recovery), maintained in the self-service (column added by init_db).
  properties:
    contextDataName:
      type: StringContextDataItemName
      id: ctxDataItemNameEmailAlt
      displayName: String Context Data 'email_alt'
      properties:
        contextDataName: email_alt""",n)
    L[j:j]=y(MTAN_CTX_ITEM,n)
    # ---- 2. Adminapp user detail
    i,j=step_range(L,'responsibleAdminLabel'); n=ind(L[i])
    L[j:j]=y("""- type: StringUserProfileItem
  id: emailAltLabel
  displayName: Alternate Email Admintool Label
  properties:
    propertyName: email_alt
    stringResourceKey: userdata.label.email-alt
- type: StringUserProfileItem
  id: recoveryConfirmedByLabel
  displayName: Recovery Confirmed By Admintool Label
  comment: Written through the Adminapp REST API by the self-service "Confirm account recovery" - REST can only write context data shown as editable user profile items.
  properties:
    propertyName: recovery_confirmed_by
    stringResourceKey: userdata.label.recovery-confirmed-by
- type: StringUserProfileItem
  id: recoveryRequestLabel
  displayName: Recovery Request Code Admintool Label
  comment: Searched and read through the Adminapp REST API by the self-service "Confirm account recovery" - REST filters and reads only context data with a user profile item.
  properties:
    propertyName: recovery_request
    stringResourceKey: userdata.label.recovery-request
- type: StringUserProfileItem
  id: recoveryRequestUntilLabel
  displayName: Recovery Request Expiry Admintool Label
  comment: Read through the Adminapp REST API (expiry of the recovery request, epoch seconds).
  properties:
    propertyName: recovery_request_until
    stringResourceKey: userdata.label.recovery-request-until""",n)
    L[j:j]=y(MTAN_PROFILE_ITEM,n)
    # ---- 3. recovery flow
    s0,s1=step_range(L,'recoveryPasswordStep')
    i,j=step_range(L,'recoveryEmailOtpStep')
    email_step=L[i:j]; n=ind(L[i])
    rel=[l[n:] if l.strip() else l for l in email_step]
    t='\n'.join(rel)
    # tag ACCOUNT_RECOVERY: only at the end of the recovery (moved to the deletion step)
    m=re.search(r'\n( *)- type: TagConfigImpl\n\1  id: accountRecovery\n(?:\1  .*\n)+',t+'\n')
    assert m
    tagdef=m.group(0).strip('\n'); tagind=len(m.group(1))
    t=(t+'\n').replace(m.group(0),'\n').rstrip('\n')
    t=t.replace("displayName: Email OTP Authentication Step (recovery, no opt-in required)","displayName: Recovery - Email OTP to the Primary Address")
    email_rel=t
    tag_rel='\n'.join(l[tagind:] for l in tagdef.split('\n'))
    steps=[]
    # users without a second factor have nothing to recover: marked here (tag), all recovery steps up to
    # the registration of a factor (and the notifications) are skipped for them
    steps.append("""- type: NoOperationStep
  id: recoveryNoFactorMark
  displayName: Recovery - User Without Second Factor (tag, recovery steps skipped)
  properties:
    skipCondition:
      ref: hasAnySecondFactor
    tagsOnSuccess:
    - pluginList:
      - type: TagConfigImpl
        id: recoveryNoFactorTag
        displayName: Recovery Without Second Factor Tag
        properties:
          name: RECOVERY_NO_FACTOR""")
    nofactor_from=len(steps)
    steps.append(email_rel)
    # known browser (automatic, 10 points): selection without user interaction
    steps.append(f"""- type: SelectionStep
  id: recoveryKnownBrowserSelection
  displayName: Recovery - Known Browser (automatic, 10 points)
  comment: The only option is available on a device the user logged in before (new device cookie); selected automatically. The Login From New Device step at the end of the flow records the device.
  properties:
    availableOptions:
    - pluginList:
      - type: SelectionOption
        id: recoveryKnownBrowserOption
        displayName: Recovery - Known Browser Option
        properties:
          condition:
{blk(not_('recoveryKnownDevice','Recovery - Known Device',"""type: NewDeviceCondition
id: recoveryNewDevice
displayName: Recovery - New Device (no login on this device before)
properties:
  cookieSettings:
    ref: loginFromNewDeviceCookie"""),12)}
          name: RECOVERY_KNOWN_BROWSER
          steps:
          - pluginList:
            - type: ScriptableStep
              id: recoveryKnownBrowserPoints
              displayName: Recovery - Known Browser (10 points)
              properties:
                namespace:
                  ref: recoveryKnownBrowserNamespace
                outputs:
                - pluginMap:
{blk(output('knownBrowserDone','recoveryKnownBrowserOutDone','B'),20)}
{blk(output('knownBrowserPoints','recoveryKnownBrowserOutPoints','S'),20)}
                script: |
                  function iam_on_step_init ()
                      return {{ knownBrowserDone = true, knownBrowserPoints = "10" }}
                  end
    fallbackFlow:
    - pluginList:
      - type: NoOperationStep
        id: recoveryKnownBrowserNone
        displayName: Recovery - Unknown Browser (no points)""")
    steps.append(W.restore_step([m[0][0].lower()+m[0][1:] for m in METHODS],ROUNDS,output,blk))
    steps.append(sum_step('recoveryTotalStart','Recovery - Points So Far (start)'))
    resumed=W.bool_restore('recoveryResumed','Recovery - Continued (saved state)','resumed')
    steps.append(msg('recoveryResumedExpiredMessage','Recovery - Continued After the Waiting Period (points so far)','recovery-resumed-expired',
                     not_('recoveryNotResumedExpired','Recovery - Not Continued After the Waiting Period',W.bool_restore('recoveryResumedExpired','Recovery - Waiting Period Over','expired')),
                     attrs=('recoveryRestoreResult',)))
    steps.append(msg('recoveryResumedPendingMessage','Recovery - Continued While Waiting (points so far, minutes left)','recovery-resumed-pending',
                     not_('recoveryNotResumedPending','Recovery - Not Continued While Waiting','ref: recoveryWaitPending'),
                     attrs=('recoveryRestoreResult',)))
    # introduction: with the known-browser bonus (says why there are 10 points) or without
    known=bool_from('recoveryKnownBrowserBonus','Recovery - Known Browser Bonus','knownBrowserDone','recoveryKnownBrowserResult')
    steps.append(msg('recoveryStartKnownMessage','Recovery - Introduction with Known Browser Bonus (points needed, points so far)','recovery-start-known',
                     f"""type: LogicalOrFlowCondition
id: recoveryStartKnownSkip
displayName: Recovery - Introduction with Bonus Skipped (no bonus, or continued)
properties:
  conditions:
  - pluginList:
{blk('- '+not_('recoveryNoKnownBrowserBonus','Recovery - No Known Browser Bonus',known).replace(chr(10),chr(10)+'  '),4)}
{blk('- '+resumed.replace(chr(10),chr(10)+'  '),4)}"""))
    steps.append(msg('recoveryStartMessage','Recovery - Introduction (points needed, points so far)','recovery-start',
                     """type: LogicalOrFlowCondition
id: recoveryStartSkip
displayName: Recovery - Introduction Skipped (bonus, or continued)
properties:
  conditions:
  - pluginList:
    - ref: recoveryKnownBrowserBonus
    - ref: recoveryResumed"""))
    # rounds
    for r in range(1,ROUNDS+1):
        opts=[]
        for k,name,pts,extra,dummy in METHODS:
            done_ref=f"recovery{k}NotDone"
            if r==1:
                done_cond=not_(f"recovery{k}NotDone",f"Recovery - {k} Not Done",bool_from(f"recovery{k}Done",f"Recovery - {k} Done",k[0].lower()+k[1:]+'Done',[f"recovery{k}Result","recoveryRestoreResult"]))
            else:
                done_cond=f"ref: {done_ref}"
            if extra:
                cond=f"""type: LogicalAndFlowCondition
id: recovery{k}AvailableR{r}
displayName: Recovery Round {r} - {k} Available
properties:
  conditions:
  - pluginList:
    - {'ref: '+extra if r>1 else 'PLACEHOLDER_EXTRA'}
{blk('- '+done_cond.replace(chr(10),chr(10)+'  '),4)}"""
                if r==1:
                    cond=cond.replace('- PLACEHOLDER_EXTRA',blk('- '+EXTRA_DEFS[extra].replace('\n','\n  '),0).replace('\n','\n    '))
            else:
                cond=done_cond
            if k=='ContactCode':
                body=contact_code_body(r)
            elif k=='ContactConfirm':
                body=contact_confirm_body(r)
            elif k=='IdDocument':
                body=I.id_body(r,L,step_range,output,blk,sum_step)
            elif k=='Wait':
                body=W.wait_body(r,[m[0][0].lower()+m[0][1:] for m in METHODS],output,blk,
                    '\n'.join(['- ref: userIdentityInfoMap','- ref: recoveryRestoreResult']+[f'- ref: recovery{m[0]}Result' for m in METHODS]))
            elif k=='Mtan':
                body=[mtan_step(r), points_script(k,pts,r,False),
                      sum_step(f"recoveryTotal{k}R{r}",f"Recovery Round {r} - Points After {k}")]
            elif dummy:
                body=[f"""- type: AcknowledgeMessageStep
  id: recovery{k}MessageR{r}
  displayName: Recovery Round {r} - {k} (example only, not available in this demo)
  properties:
    messageId: recovery-dummy""", points_script(k,pts,r,True)]
            else:
                body=[f"""- type: EmailOtpAuthenticationStep
  id: recovery{k}OtpR{r}
  displayName: Recovery Round {r} - Email OTP to the Alternate Address (8 points)
  properties:
    emailMessageProvider:
      ref: emailOtpAuthMessage
    emailService:
      ref: emailService
    maxResends: '1'
    maxRetries: '2'
    messageTemplateIsHtml: 'false'
    recipientAddress:
      ref: userEmailAltProvider""", points_script(k,pts,r,False),
                      sum_step(f"recoveryTotal{k}R{r}",f"Recovery Round {r} - Points After {k}")]
            opts.append(f"""- type: SelectionOption
  id: recovery{k}OptionR{r}
  displayName: Recovery Round {r} - {k} Option
  properties:
    condition:
{blk(cond,6)}
    name: {name}
    steps:
    - pluginList:
{blk(chr(10).join(body),6)}""")
        opts.append(W.pending_option(r,blk))
        reached=bool_from('recoveryReached','Recovery - Points Reached','reached','recoveryTotalResult') if r==1 else 'ref: recoveryReached'
        skip=f"""type: LogicalOrFlowCondition
id: recoveryRound{r}Skip
displayName: Recovery Round {r} - Skipped (points reached, or continued in a later round)
properties:
  conditions:
  - pluginList:
{blk('- '+reached.replace(chr(10),chr(10)+'  '),4)}
{blk('- '+W.bool_restore(f'recoveryRestoreSkipR{r}',f'Recovery - Continue After Round {r}',f'skipR{r}').replace(chr(10),chr(10)+'  '),4)}"""
        steps.append(f"""- type: SelectionStep
  id: recoveryRound{r}
  displayName: Recovery - Confirmation Round {r} of {ROUNDS} (skipped once the points are reached)
  comment: Step ID recovery-round-{r} - the design kit text custom.step.recovery-round-{r}.authentication.selection.instructions shows the points so far ({{{{ customAttributes.total }}}} of {{{{ customAttributes.threshold }}}}).
  properties:
    autoSelectOnlyOption: 'false'
    customResponseAttributes:
    - pluginList:
      - ref: recoveryTotalResult
    stepId:
      type: StepId
      id: recoveryRoundStepIdR{r}
      displayName: Recovery Round {r} Step ID "recovery-round-{r}"
      properties:
        id: recovery-round-{r}
    availableOptions:
    - pluginList:
{blk(chr(10).join(opts),6)}
    fallbackFlow:
    - pluginList:
      - type: NoOperationStep
        id: recoveryRound{r}NoOptions
        displayName: Recovery Round {r} - No Confirmation Left
    skipCondition:
{blk(skip,6)}""")
    steps.append(W.clear_state('recoveryStateClearNotPossible','Recovery - Saved State Deleted (not enough points)','ref: recoveryReached',blk))
    steps.append(msg('recoveryNotPossibleMessage','Recovery - Not Enough Points (contact the helpdesk)','recovery-not-possible','ref: recoveryReached'))
    steps.append("""- type: AbortStep
  id: recoveryNotPossibleAbort
  displayName: Recovery - Not Enough Points (abort)
  properties:
    errorCode: RECOVERY_NOT_POSSIBLE
    skipCondition:
      ref: recoveryReached""")
    steps.append(f"""- type: ScriptableStep
  id: recoveryDeleteFactorsStep
  displayName: Recovery - Delete All Second Factors (Adminapp REST API)
  properties:
    inputs:
    - pluginList:
      - ref: userIdentityInfoMap
    inputSecrets:
    - pluginList:
      - ref: selfRegLookupPasswordSecret
    namespace:
      type: ScriptNamespace
      id: recoveryDeleteNamespace
      displayName: Script Namespace recovery-delete
      properties:
        identifier: recovery-delete
    outputs:
    - pluginMap:
{blk(output('deleted','recoveryDeleteOutDeleted','S'),8)}
    tagsOnSuccess:
    - pluginList:
{blk(tag_rel,6)}
    script: |
{blk(DELETE_SCRIPT,6)}""")
    steps.append(W.clear_state('recoveryStateClearSuccess','Recovery - Saved State Deleted (recovered)',blk=blk))
    steps.append("- type: NonInteractiveSetContextDataStep\n  id: recoveryEmailOtpOff\n  displayName: Recovery - Email OTP Opt-in Off, Preferred Login Method Unset\n  properties:\n    userDataItems:\n    - pluginList:\n      - type: BooleanNonInteractiveUserDataItemDefinition\n        id: recoveryEmailOtpOffItem\n        displayName: Email OTP Enabled = false (recovery)\n        properties:\n          contextDataItemNameConfig:\n            ref: ctxDataItemNameEmailOtpEnabled\n          valueProviderConfig:\n            type: BooleanStaticValueProvider\n            id: staticFalse\n            displayName: Static False\n            properties:\n              value: 'false'\n      - type: StringNonInteractiveUserDataItemDefinition\n        id: recoveryAuthMethodUnset\n        displayName: auth_method = empty (recovery - the new factor sets it, unset if none is registered)\n        properties:\n          contextDataItemNameConfig:\n            ref: ctxDataItemNameAuthMethod\n          valueProviderConfig:\n            type: StringStaticValueProvider\n            id: recoveryAuthMethodEmpty\n            displayName: Value auth_method empty (recovery)\n            properties:\n              value: ''")
    steps.append("- ref: factorRegistrationSelectionStep")
    steps.append("""- type: EmailNotificationStep
  id: recoveryNotifyPrimary
  displayName: Recovery - Notification to the Primary Address
  properties:
    emailService:
      ref: emailService
    recipientAddressProvider:
      ref: userEmailProvider
    subjectResourceKey: custom.recovery.email.reset.subject
    bodyResourceKey: custom.recovery.email.reset.body
    valueMapProviders:
    - pluginList:
      - ref: userContextDataMap""")
    steps.append("""- type: EmailNotificationStep
  id: recoveryNotifyAlternate
  displayName: Recovery - Notification to the Alternate Address
  properties:
    emailService:
      ref: emailService
    recipientAddressProvider:
      ref: userEmailAltProvider
    skipCondition:
      type: LogicalNotFlowCondition
      id: noEmailAlt
      displayName: No Alternate Email Address
      properties:
        condition:
          ref: hasEmailAlt
    subjectResourceKey: custom.recovery.email.reset.subject
    bodyResourceKey: custom.recovery.email.reset.body
    valueMapProviders:
    - pluginList:
      - ref: userContextDataMap""")
    steps.append("- ref: loginFromNewDeviceStep")
    # skip all steps from the email OTP to the deletion and the notifications for users without a factor
    def add_nofactor_skip(st, first, idx):
        cond = ('type: TagCondition\nid: recoveryNoFactor\ndisplayName: Recovery - User Had No Second Factor\n'
                'properties:\n  tag:\n    ref: recoveryNoFactorTag') if first else 'ref: recoveryNoFactor'
        L2=st.split('\n')
        k=[x for x,l in enumerate(L2) if l=='    skipCondition:']
        if not k:
            i=[x for x,l in enumerate(L2) if l=='  properties:'][0]
            L2[i+1:i+1]=['    skipCondition:']+y(cond,6)
            return '\n'.join(L2)
        k=k[0]; e=k+1
        while e<len(L2) and (L2[e].strip()=='' or len(L2[e])-len(L2[e].lstrip(' '))>4): e+=1
        old=[l[6:] for l in L2[k+1:e]]
        orid=f"recoverySkipOrNoFactor{idx}"
        new=['type: LogicalOrFlowCondition','id: '+orid,'displayName: Recovery - Skip Condition or No Second Factor (step '+str(idx)+')','properties:','  conditions:','  - pluginList:']
        new+=y('- '+'\n'.join(old).replace('\n','\n  '),4)+y('- '+cond.replace('\n','\n  '),4)
        L2[k+1:e]=y('\n'.join(new),6)
        return '\n'.join(L2)
    first=True
    for x in range(nofactor_from, len(steps)):
        st=steps[x]
        if st.startswith('- ref: factorRegistrationSelectionStep'): continue
        if st.startswith('- ref: loginFromNewDeviceStep'): continue
        steps[x]=add_nofactor_skip(st, first, x); first=False
    new_steps=[l for st in steps for l in y(st,n)]
    # the namespaces/result providers: defined once inside the first sum step's inputs -> replace refs there
    L[s1:j]=new_steps
    t='\n'.join(L)
    # define result providers (with namespaces) at their first reference
    for k in ['KnownBrowser']+[m[0] for m in METHODS]:
        mm=re.search(r'\n( *)- ref: recovery'+k+r'Result\n',t)
        assert mm,k
        nn=len(mm.group(1))
        d=[x for x in NAMESPACES.split('\n- type:')]
        one=[x for x in NAMESPACES.split('\n') ]
        # extract the k block
        parts=re.split(r'\n(?=- type: )',NAMESPACES)
        b=[x for x in parts if f'id: recovery{k}Result' in x][0]
        t=t[:mm.start()]+'\n'+blk(b,nn)+'\n'+t[mm.end():]
    # the namespace refs inside points scripts point to these definitions; the first use of
    # recoveryTotalNamespace / recoveryTotalResult needs a definition too
    mm=re.search(r'\n( *)ref: recoveryTotalNamespace\n',t)
    nn=len(mm.group(1))
    t=t[:mm.start()]+'\n'+' '*nn+'type: ScriptNamespace\n'+' '*nn+'id: recoveryTotalNamespace\n'+' '*nn+'displayName: Script Namespace recovery-total\n'+' '*nn+'properties:\n'+' '*nn+'  identifier: recovery-total\n'+t[mm.end():]
    mm=re.search(r'\n( *)- ref: recoveryTotalResult\n',t)
    nn=len(mm.group(1))
    t=t[:mm.start()]+'\n'+blk("""- type: ScriptExecutionResultValueMapProvider
  id: recoveryTotalResult
  displayName: Recovery Points (sum)
  properties:
    namespaceConfig:
      ref: recoveryTotalNamespace""",nn)+'\n'+t[mm.end():]
    t=t.replace("displayName: Account Recovery Flow (password and email code)","displayName: Account Recovery Flow (password, email code, confirmations with points, new second factor)")
    for pid,d in SMS_DEFS.items():
        t=define_first(t,pid,d)
    for pid,d in (('recoveryRestoreResult',W.RESTORE_RESULT_DEF),('recoveryWaitStartResult',W.WAIT_START_RESULT_DEF)):
        t=define_first(t,pid,d)
    L=t.split('\n')
    # ---- 4. self-service: alternate email address
    a,b=step_range(L,'emailChangeFlow'); n2=ind(L[a])
    L[b:b]=y("""- type: CustomProtectedSelfServiceFlow
  id: emailAltChangeFlow
  displayName: Alternate Email Address Flow
  comment: Alternate email address for the account recovery (context data email_alt), verified with a code sent to it.
  properties:
    flowId:
      type: FlowId
      id: emailAltChangeFlowId
      displayName: Flow ID "email-alt-change"
      properties:
        flowId: email-alt-change
    steps:
    - pluginList:
      - type: UserDataEditStep
        id: emailAltEditStep
        displayName: Edit Alternate Email Address Step
        properties:
          stepId:
            type: StepId
            id: emailAltEditStepId
            displayName: Alternate Email Step ID 'edit-email-alt'
            properties:
              id: edit-email-alt
          userDataItems:
          - pluginList:
            - type: EmailItemDefinition
              id: emailAltItem
              displayName: Alternate Email Address
              properties:
                enableStealthMode: 'false'
                initialValueProvider:
                  ref: userEmailAltProvider
                inputPurpose: email
                key: email_alt
                unique: 'false'
      - type: EmailChangeVerificationStep
        id: emailAltVerificationStep
        displayName: Alternate Email Verification Step
        properties:
          emailItem:
            ref: emailAltItem
          emailMessageProvider:
            ref: emailChangeMessage
          emailProvider:
            ref: changedEmailProvider
          emailService:
            ref: emailService
          otpGenerator:
            ref: pwdResetOtpGenerator
      - type: ApplyChangesStep
        id: emailAltApply
        displayName: Persist Alternate Email Address Step
        properties:
          handlers:
          - pluginList:
            - type: ApplyEmailChange
              id: emailAltApplyHandler
              displayName: Apply Alternate Email Address
              properties:
                contextDataName:
                  ref: ctxDataItemNameEmailAlt""",n2)
    a,b=step_range(L,'emailAltChangeFlow')
    L[b:b]=y(MTAN_CHANGE_FLOW,ind(L[a]))
    a,b=step_range(L,'mtanNumberChangeFlow')
    L[b:b]=y(I.selfservice_flow(output,blk),ind(L[a]))
    a,b=step_range(L,'emailAltChangeFlow')
    L[b:b]=y(f"""- type: CustomProtectedSelfServiceFlow
  id: recoveryConfirmFlow
  displayName: Confirm Account Recovery (administrators)
  comment: An administrator who received a recovery request by email enters its code; the recovering user then gets 20 points. Only contacts of that user may confirm (partner administrators of the realm, else mgr-partners / mgr-admins).
  properties:
    accessCondition:
      ref: hasAdminOrPartnerAdminRole
    flowId:
      type: FlowId
      id: recoveryConfirmFlowId
      displayName: Flow ID "recovery-confirm"
      properties:
        flowId: recovery-confirm
    steps:
    - pluginList:
      - type: UserDataEditStep
        id: recoveryConfirmCodeEntry
        displayName: Confirm Account Recovery - Enter Code
        properties:
          stepId:
            type: StepId
            id: recoveryConfirmCodeEntryStepId
            displayName: Confirm Account Recovery Code Entry Step ID "recovery-confirm-code"
            properties:
              id: recovery-confirm-code
          userDataItems:
          - pluginList:
{blk(code_item('recoveryConfirmCodeItem','Confirm Account Recovery - Code (input)'),12)}
{blk(lua_step('recoveryConfirmStep','Confirm Account Recovery - Check and Confirm (Adminapp REST API)',"""type: ScriptNamespace
id: recoveryConfirmNamespace
displayName: Script Namespace recovery-confirm
properties:
  identifier: recovery-confirm""",[output('result','recoveryConfirmOutResult','S')],CONFIRM_SELFSERVICE,inputs=('userIdentityInfoMap','recoveryEditedCodeMap')),6)}
      - type: AcknowledgeMessageStep
        id: recoveryConfirmResultStep
        displayName: Confirm Account Recovery - Result
        properties:
          messageId: recovery-confirm-result
          serverMessage:
            type: TranslationValueProvider
            id: recoveryConfirmResultText
            displayName: Confirm Account Recovery - Result Text
            properties:
              resourceKey: custom.recovery.confirm.result.${{result}}
              valueProviders:
              - pluginList:
                - type: ScriptExecutionResultValueMapProvider
                  id: recoveryConfirmResult
                  displayName: Confirm Account Recovery Result
                  properties:
                    namespaceConfig:
                      ref: recoveryConfirmNamespace""",ind(L[a]))
    a,b=step_range(L,'preferredAuthMethodUi')
    L[b:b]=y("""- type: SelfServiceUi
  id: recoveryConfirmUi
  displayName: Confirm Account Recovery UI
  properties:
    cancellationTarget:
      ref: redirectToAuth
    completionTarget:
      ref: redirectToAuth
    flowId:
      ref: recoveryConfirmFlowId
    maintenanceMessageUiSettings:
      ref: maintMsgUi
    showConfirmationPage: 'false'""",ind(L[a]))
    a,b=step_range(L,'portalTarget-config-restore')
    L[b:b]=y("""- type: ApplicationPortalTarget
  id: portalTarget-recovery-confirm
  displayName: Application Portal Target Confirm Account Recovery
  properties:
    identifier: recovery-confirm
    precondition:
      ref: hasAdminOrPartnerAdminRole
    redirectByAccess: 'false'
    redirectTarget:
      type: SelfServiceFlowRedirectTarget
      id: redirect-recovery-confirm
      displayName: Portal Redirect Confirm Account Recovery
      properties:
        flowId:
          ref: recoveryConfirmFlowId""",ind(L[a]))
    a,b=step_range(L,'preferredAuthMethodUi')
    L[b:b]=y("""- type: SelfServiceUi
  id: emailAltChangeUi
  displayName: Alternate Email Address UI
  properties:
    cancellationTarget:
      ref: redirectToAuth
    completionTarget:
      ref: redirectToAuth
    flowId:
      ref: emailAltChangeFlowId
    maintenanceMessageUiSettings:
      ref: maintMsgUi
    showConfirmationPage: 'false'""",ind(L[a]))
    a,b=step_range(L,'portalTarget-email-address-change')
    L[b:b]=y("""- type: ApplicationPortalTarget
  id: portalTarget-email-alt-change
  displayName: Application Portal Target Alternate Email Address
  properties:
    identifier: email-alt-change
    redirectByAccess: 'false'
    redirectTarget:
      type: SelfServiceFlowRedirectTarget
      id: redirect-email-alt-change
      displayName: Portal Redirect Alternate Email Address
      properties:
        flowId:
          ref: emailAltChangeFlowId""",ind(L[a]))
    a,b=step_range(L,'emailAltChangeUi')
    L[b:b]=y(MTAN_CHANGE_UI,ind(L[a]))
    a,b=step_range(L,'portalTarget-email-alt-change')
    L[b:b]=y(MTAN_CHANGE_PORTAL,ind(L[a]))
    a,b=step_range(L,'mtanNumberChangeUi')
    L[b:b]=y(I.IDENTITY_UI,ind(L[a]))
    a,b=step_range(L,'portalTarget-mtan-number-change')
    L[b:b]=y(I.IDENTITY_PORTAL,ind(L[a]))
    a,b=step_range(L,'configRestoreStepUpApp')
    L[b:b]=y(I.STEP_UP_APP,ind(L[a]))
    a,b=step_range(L,'configRestoreStepUpUi')
    L[b:b]=y(I.STEP_UP_UI,ind(L[a]))
    t='\n'.join(L)
    t=define_first(t,'identityCompareResult',I.IDENTITY_RESULT_DEF)
    L=t.split('\n')
    a,_=step_range(L,'rememberMeTokenGeneratingStep')
    L[a:a]=y(W.clear_state(W.LOGIN_CANCEL_STEP_ID,'Login - Cancel a Saved Account Recovery (normal login)',"""type: LogicalNotFlowCondition
id: noSavedRecovery
displayName: No Saved Account Recovery
properties:
  condition:
    type: StringRegexCondition
    id: hasSavedRecovery
    displayName: Has Saved Account Recovery (context data recovery_state)
    properties:
      regexPattern: .+
      valueProvider:
        type: ContextDataStringValueProvider
        id: userRecoveryStateProvider
        displayName: Existing Saved Recovery State
        properties:
          contextDataField:
            ref: ctxDataItemRecoveryStateName""",blk),ind(L[a]))
    open(p,'w').write('\n'.join(L))
    print(p,'ok')

if __name__ == '__main__':
    if len(sys.argv)!=2: sys.exit(__doc__)
    print('previous output removed' if strip(sys.argv[1]) else 'no previous output')
    build(sys.argv[1])
