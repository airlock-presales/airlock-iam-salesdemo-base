# Identity document (phase E): self-service "Verify identity" and recovery method "ID document"
#
# Self-service (flow identity-verification): PXL Vision check (the steps of the self-registration, reused by
# reference), then the document number and type are stored (context data idp_doc_number, idp_doc_type; the
# latest check overwrites); country = issuing country of the document (overwritten silently). First and last name:
# filled in if empty; if they differ
# from the document, the user is asked whether to update them. Requires a second factor of this session
# (authorization condition: tag STRONG_AUTHENTICATION) - step-up application identity-step-up.
#
# Recovery method "ID document" (25 points): only with a stored document. A hint page names the stored document
# type, then a PXL Vision check (per round own copies of the steps: the "back to the QR code" goto needs a unique
# step ID); same type and number (normalized) -> 25 points.
import re
import yaml

ID_POINTS = 25

# PXL Vision document types (documentation): text key suffix of the hint page; card and id are not explained,
# one of them is the identity card - both get the identity card text
DOC_TYPES = [('passport', '^passport$'), ('health-card', '^healthCard$'), ('identity-card', '^(card|id)$'),
             ('driving-licence', '^drivingLicence$')]


class _Literal(str):
    pass


def _literal_representer(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')


yaml.add_representer(_Literal, _literal_representer)


def _to_refs(node, depth=0):
    """plugins defined inline become references (they are defined in the original step)"""
    if isinstance(node, dict):
        if depth > 0 and 'type' in node and 'id' in node:
            return {'ref': node['id']}
        return {k: _to_refs(v, depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        return [_to_refs(v, depth + 1) for v in node]
    if isinstance(node, str) and '\n' in node:
        return _Literal(node)
    return node


def copy_step(L, step_range, step_id, new_id, new_disp, extra=None):
    """copy of a step of the configuration with a new ID: its inline plugins as references"""
    i, j = step_range(L, step_id)
    n = len(L[i]) - len(L[i].lstrip(' '))
    plugin = yaml.safe_load('\n'.join(l[n:] if l.strip() else l for l in L[i:j]))[0]
    props = _to_refs(plugin['properties'], 1)
    props.pop('stepId', None)
    if extra:
        props.update(extra)
    out = {'type': plugin['type'], 'id': new_id, 'displayName': new_disp, 'properties': props}
    return yaml.dump([out], default_flow_style=False, sort_keys=False, width=1000, allow_unicode=True).rstrip('\n')


def regex_cond(id_, disp, pattern, provider):
    return f"""type: StringRegexCondition
id: {id_}
displayName: {disp}
properties:
  regexPattern: {pattern}
  valueProvider:
{provider}"""


HAS_ID_DOCUMENT_DEF = """type: StringRegexCondition
id: hasIdDocument
displayName: Has Stored ID Document (context data idp_doc_number)
properties:
  regexPattern: .+
  valueProvider:
    type: ContextDataStringValueProvider
    id: userIdpDocNumberProvider
    displayName: Existing ID Document Number
    properties:
      contextDataField:
        ref: ctxDataItemNameIdpDocNumber"""

DOC_TYPE_PROVIDER_DEF = """    type: ContextDataStringValueProvider
    id: userIdpDocTypeProvider
    displayName: Existing ID Document Type
    properties:
      contextDataField:
        ref: ctxDataItemNameIdpDocType"""

COMPARE_SCRIPT = r'''-- account recovery: ID document - compare the checked document with the stored one (type and number)
local POINTS = %d
local function norm (value)
    return (tostring(value or ""):upper():gsub("[^%%w]", ""))
end
function iam_on_step_init ()
    local done = iam.input_map["kycDone"] == true or iam.input_map["kycDone"] == "true"
    local number = norm(iam.input_map["documentNumber"])
    local ok = done and number ~= "" and number == norm(iam.input_map["idp_doc_number"])
        and tostring(iam.input_map["documentType"] or "") == tostring(iam.input_map["idp_doc_type"] or "")
    iam.log:info("Recovery: ID document of " .. tostring(iam.input_map["user-id"]) .. (not done and " - check not completed"
        or (ok and " matches" or " does not match (type " .. tostring(iam.input_map["documentType"]) .. ")")))
    return { idDocumentDone = ok, idDocumentPoints = ok and tostring(POINTS) or "0", idDocumentOk = ok }
end''' % ID_POINTS


def id_body(r, L, step_range, output, blk, sum_step):
    """recovery round r: PXL Vision check (the QR code page names the stored document type), comparison, points"""
    steps = []
    steps.append(copy_step(L, step_range, 'pxlAuthenticateStep', f'recoveryIdAuthR{r}',
                           f'Recovery Round {r} - ID Document - PXL Vision Authenticate'))
    steps.append(copy_step(L, step_range, 'pxlTransactionStep', f'recoveryIdTransactionR{r}',
                           f'Recovery Round {r} - ID Document - PXL Vision Start Transaction'))
    # goto target of "back to the QR code": a marker step in front of the launch page variants
    steps.append(f"""- type: NoOperationStep
  id: recoveryIdLaunchR{r}
  displayName: Recovery Round {r} - ID Document - Launch (marker, goto target of "back to the QR code")
  properties:
    stepId:
      type: StepId
      id: recoveryIdLaunchStepIdR{r}
      displayName: Recovery Round {r} ID Document Launch Step ID "recovery-id-launch-{r}"
      properties:
        id: recovery-id-launch-{r}""")
    # launch page (link and QR code) - one variant per stored document type, the others skipped
    if r == 1:
        doc_type_map = """      - type: ValueProviderMapProvider
        id: recoveryIdDocTypeMap
        displayName: Recovery - Stored ID Document Type (docType)
        properties:
          valueProviders:
          - pluginMap:
              docType:
                type: ContextDataStringValueProvider
                id: userIdpDocTypeProvider
                displayName: Existing ID Document Type
                properties:
                  contextDataField:
                    ref: ctxDataItemNameIdpDocType
"""
    else:
        doc_type_map = "      - ref: recoveryIdDocTypeMap\n"
    def attrs(first):
        """response attributes of a launch page: transaction code, stored document type (defined once)"""
        return """    customResponseAttributes:
    - pluginList:
      - ref: pxlTransactionResult
""" + (doc_type_map if first else "      - ref: recoveryIdDocTypeMap\n")
    known = []
    for key, pattern in DOC_TYPES:
        cid = ''.join(x.title() for x in key.split('-'))
        cond_id = f'idDocType{cid}'
        cond = (regex_cond(cond_id, f'Stored ID Document Type is {key}', pattern, '    ref: userIdpDocTypeProvider')
                if r == 1 else f'ref: {cond_id}')
        known.append(cond_id)
        steps.append(f"""- type: AcknowledgeMessageStep
  id: recoveryIdLaunch{cid}R{r}
  displayName: Recovery Round {r} - ID Document - Launch ({key}, link and QR code)
  properties:
    messageId: recovery-id-launch-{key}
{attrs(not known[:-1])}    skipCondition:
      type: LogicalNotFlowCondition
      id: recoveryIdLaunchNot{cid}R{r}
      displayName: Recovery Round {r} - ID Document - Not {key}
      properties:
        condition:
{blk(cond, 10)}""")
    other = '\n'.join('    - ref: ' + c for c in known)
    steps.append(f"""- type: AcknowledgeMessageStep
  id: recoveryIdLaunchOtherR{r}
  displayName: Recovery Round {r} - ID Document - Launch (other type, link and QR code)
  properties:
    messageId: recovery-id-launch-other
{attrs(False)}    skipCondition:
{blk(f'''type: LogicalOrFlowCondition
id: recoveryIdLaunchKnownR{r}
displayName: Recovery Round {r} - ID Document - Known Type
properties:
  conditions:
  - pluginList:
{other}''', 6)}""")
    steps.append(copy_step(L, step_range, 'pxlResultStep', f'recoveryIdResultR{r}',
                           f'Recovery Round {r} - ID Document - PXL Vision Get Result (waits up to 20 seconds)'))
    steps.append(f"""- type: AcknowledgeMessageStep
  id: recoveryIdNotCompletedR{r}
  displayName: Recovery Round {r} - ID Document - Not Completed Yet (back to the QR code)
  properties:
    messageId: recovery-id-not-completed
    stepId:
      type: StepId
      id: recoveryIdNotCompletedStepIdR{r}
      displayName: Recovery Round {r} ID Document Not Completed Step ID "recovery-id-not-completed-{r}"
      properties:
        id: recovery-id-not-completed-{r}
    interactiveGotoTargets:
    - pluginList:
      - type: InteractiveGotoTarget
        id: recoveryIdBackToLaunchR{r}
        displayName: Recovery Round {r} - ID Document - Back to the QR Code
        properties:
          targetStepId:
            ref: recoveryIdLaunchStepIdR{r}
    skipCondition:
      ref: pxlKycDone""")
    compare_ns = ("ref: recoveryIdDocumentNamespace")
    steps.append(f"""- type: ScriptableStep
  id: recoveryIdCompareR{r}
  displayName: Recovery Round {r} - ID Document - Compare with the Stored Document ({ID_POINTS} points)
  properties:
    inputs:
    - pluginList:
      - ref: pxlResult
      - ref: userContextDataMap
      - ref: userIdentityInfoMap
    namespace:
      {compare_ns}
    outputs:
    - pluginMap:
{blk(output('idDocumentDone', f'recoveryIdDocumentOutDoneR{r}', 'B'), 8)}
{blk(output('idDocumentPoints', f'recoveryIdDocumentOutPointsR{r}', 'S'), 8)}
{blk(output('idDocumentOk', f'recoveryIdDocumentOutOkR{r}', 'B'), 8)}
    script: |
{blk(COMPARE_SCRIPT, 6)}""")
    steps.append(sum_step(f'recoveryTotalIdDocumentR{r}', f'Recovery Round {r} - Points After ID Document'))
    ok_cond = ("""type: BooleanCondition
id: recoveryIdDocumentOk
displayName: Recovery - ID Document Matches
properties:
  valueProvider:
    type: BooleanFromMapValueProvider
    id: recoveryIdDocumentOkValue
    displayName: Recovery - ID Document Matches (value "idDocumentOk")
    properties:
      key: idDocumentOk
      provideFalseIfEmpty: 'true'
      valueMaps:
      - pluginList:
        - ref: recoveryIdDocumentResult""" if r == 1 else 'ref: recoveryIdDocumentOk')
    steps.append(f"""- type: AcknowledgeMessageStep
  id: recoveryIdWrongR{r}
  displayName: Recovery Round {r} - ID Document - No Match or Not Completed (message)
  properties:
    messageId: recovery-id-wrong
    skipCondition:
{blk(ok_cond, 6)}""")
    return steps


# ------------------------------------------------------------------ self-service "Verify identity"
SS_COMPARE_SCRIPT = r'''-- self-service "Verify identity": compare first and last name of the document with the profile (the birthdate
-- is neither read nor stored - data minimization)
-- keep*: profile values (document values only where the profile is empty); upd*: document values (profile values
-- where the document has none); differs: a non-empty profile value differs from the document -> the user decides
local function s (value)
    if type(value) ~= "string" then return "" end
    return (value:gsub("^%s+", ""):gsub("%s+$", ""))
end
local function trim (value)
    return (value:gsub("^%s+", ""):gsub("%s+$", ""))
end
function iam_on_step_init ()
    local out = { done = false, differs = false, docName = "", storedName = "",
        keepGivenname = "", keepSurname = "", updGivenname = "", updSurname = "" }
    if not (iam.input_map["kycDone"] == true or iam.input_map["kycDone"] == "true") then return out end
    out.done = true
    local dg, ds = s(iam.input_map["firstName"]), s(iam.input_map["lastName"])
    local sg, ss = s(iam.input_map["givenname"]), s(iam.input_map["surname"])
    local function differ (stored, doc)
        return stored ~= "" and doc ~= "" and stored:lower() ~= doc:lower()
    end
    out.differs = differ(sg, dg) or differ(ss, ds)
    out.keepGivenname = sg ~= "" and sg or dg
    out.keepSurname = ss ~= "" and ss or ds
    out.updGivenname = dg ~= "" and dg or sg
    out.updSurname = ds ~= "" and ds or ss
    out.docName = trim(dg .. " " .. ds)
    out.storedName = trim(sg .. " " .. ss)
    return out
end'''


def _set_names(id_, disp, prefix):
    items = []
    for field, ctx in (('Givenname', 'ctxDataItemNameGivenname'), ('Surname', 'ctxDataItemNameSurname')):
        items.append(f"""- type: StringNonInteractiveUserDataItemDefinition
  id: {id_}{field}
  displayName: {disp} - {field.lower()}
  properties:
    contextDataItemNameConfig:
      ref: {ctx}
    valueProviderConfig:
      type: StringFromMapValueProvider
      id: {id_}{field}Value
      displayName: {disp} - Value "{prefix}{field}"
      properties:
        key: {prefix}{field}
        valueMaps:
        - pluginList:
          - ref: identityCompareResult""")
    body = '\n'.join(items).replace('\n', '\n      ')
    return f"""- type: NonInteractiveSetContextDataStep
  id: {id_}
  displayName: {disp}
  properties:
    userDataItems:
    - pluginList:
      {body}"""


def _bool_compare(id_, disp, key):
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
        - ref: identityCompareResult"""


def selfservice_flow(output, blk):
    outs = [output(k, f'identityCompareOut{k[0].upper()}{k[1:]}', 'B') for k in ('done', 'differs')]
    outs += [output(k, f'identityCompareOut{k[0].upper()}{k[1:]}', 'S') for k in
             ('docName', 'storedName', 'keepGivenname', 'keepSurname', 'updGivenname', 'updSurname')]
    compare = f"""- type: ScriptableStep
  id: identityCompareStep
  displayName: Verify Identity - Compare the Name with the Profile
  properties:
    inputs:
    - pluginList:
      - ref: pxlResult
      - ref: userContextDataMap
    namespace:
      type: ScriptNamespace
      id: identityCompareNamespace
      displayName: Script Namespace identity-compare
      properties:
        identifier: identity-compare
    outputs:
    - pluginMap:
{blk(chr(10).join(outs), 8)}
    script: |
{blk(SS_COMPARE_SCRIPT, 6)}"""
    done = _bool_compare('identityDone', 'Verify Identity - Check Completed', 'done')
    differs = _bool_compare('identityDiffers', 'Verify Identity - Name Differs', 'differs')
    not_done = f"""type: LogicalNotFlowCondition
id: identityNotDone
displayName: Verify Identity - Check Not Completed
properties:
  condition:
{blk(done, 4)}"""
    doc = """- type: NonInteractiveSetContextDataStep
  id: identityDocStore
  displayName: Verify Identity - Store the Document (number, type)
  properties:
    skipCondition:
      ref: identityNotDone
    userDataItems:
    - pluginList:
      - type: StringNonInteractiveUserDataItemDefinition
        id: identityDocNumber
        displayName: Verify Identity - Document Number
        properties:
          contextDataItemNameConfig:
            ref: ctxDataItemNameIdpDocNumber
          valueProviderConfig:
            ref: pxlDocNumberValue
      - type: StringNonInteractiveUserDataItemDefinition
        id: identityDocType
        displayName: Verify Identity - Document Type
        properties:
          contextDataItemNameConfig:
            ref: ctxDataItemNameIdpDocType
          valueProviderConfig:
            ref: pxlDocTypeValue
- type: NonInteractiveSetContextDataStep
  id: identityCountryStore
  displayName: Verify Identity - Country from the Document (issuing country, overwritten silently)
  properties:
    skipCondition:
      type: LogicalNotFlowCondition
      id: identityNoDocCountry
      displayName: Verify Identity - No Country on the Document
      properties:
        condition:
          type: StringRegexCondition
          id: identityHasDocCountry
          displayName: Verify Identity - Document Has a Country (ISO alpha-3)
          properties:
            regexPattern: .+
            valueProvider:
              ref: pxlCountryValue
    userDataItems:
    - pluginList:
      - type: StringNonInteractiveUserDataItemDefinition
        id: identityCountry
        displayName: Verify Identity - Country
        properties:
          contextDataItemNameConfig:
            ref: ctxDataItemNameCountry
          valueProviderConfig:
            ref: pxlCountryValue"""
    selection = f"""- type: SelectionStepConfigForSelfServiceFlows
  id: identityUpdateSelection
  displayName: Verify Identity - Update the Name? (only if it differs)
  comment: Step ID identity-update - the design kit texts custom.step.identity-update.protected.self-service.selection.* show both names ({{{{ customAttributes.docName }}}}, storedName).
  properties:
    autoSelectOnlyOption: 'false'
    customResponseAttributes:
    - pluginList:
      - ref: identityCompareResult
    stepId:
      type: StepId
      id: identityUpdateStepId
      displayName: Verify Identity Update Step ID "identity-update"
      properties:
        id: identity-update
    availableOptions:
    - pluginList:
      - type: SelectionOptionConfigForSelfServiceFlows
        id: identityUpdateOption
        displayName: Verify Identity - Update from the Document
        properties:
          condition:
            ref: alwaysTrue
          name: IDENTITY_UPDATE
          steps:
          - pluginList:
{blk(_set_names('identityUpdateNames', 'Verify Identity - Name from the Document', 'upd'), 12)}
      - type: SelectionOptionConfigForSelfServiceFlows
        id: identityKeepOption
        displayName: Verify Identity - Keep the Profile Data
        properties:
          condition:
            ref: alwaysTrue
          name: IDENTITY_KEEP
          steps:
          - pluginList:
{blk(_set_names('identityKeepNames', 'Verify Identity - Name Kept (empty fields from the document)', 'keep'), 12)}
    skipCondition:
      type: LogicalNotFlowCondition
      id: identityNotDiffers
      displayName: Verify Identity - Name Does Not Differ
      properties:
        condition:
{blk(differs, 10)}"""
    fill_names = _set_names('identityFillNames', 'Verify Identity - Empty Name Fields from the Document', 'keep') + """
    skipCondition:
      type: LogicalOrFlowCondition
      id: identityFillNamesSkip
      displayName: Verify Identity - No Name Filling (not completed, or the user decided)
      properties:
        conditions:
        - pluginList:
          - ref: identityNotDone
          - ref: identityDiffers"""
    msgs = """- type: AcknowledgeMessageStep
  id: identityVerifiedMessage
  displayName: Verify Identity - Document Stored (message)
  properties:
    messageId: identity-verified
    skipCondition:
      ref: identityNotDone
- type: AcknowledgeMessageStep
  id: identityNotCompletedMessage
  displayName: Verify Identity - Not Completed, Nothing Stored (message)
  properties:
    messageId: identity-not-completed
    skipCondition:
      ref: identityDone"""
    steps = '\n'.join(['- ref: pxlAuthenticateStep', '- ref: pxlTransactionStep', '- ref: pxlLaunchStep',
                       '- ref: pxlResultStep', '- ref: pxlNotCompletedStep', compare,
                       doc.replace('ref: identityNotDone', not_done.replace('\n', '\n      '), 1),
                       selection, fill_names, msgs])
    return f"""- type: CustomProtectedSelfServiceFlow
  id: identityVerificationFlow
  displayName: Verify Identity Flow (ID document, PXL Vision)
  comment: Stores the ID document (number, type) for the account recovery; requires a second factor of this session (step-up application identity-step-up).
  properties:
    accessCondition:
      ref: hasAnySecondFactor
    authorizationCondition:
      ref: hasStrongAuthTag
    flowId:
      type: FlowId
      id: identityVerificationFlowId
      displayName: Flow ID "identity-verification"
      properties:
        flowId: identity-verification
    steps:
    - pluginList:
{blk(steps, 6)}"""


IDENTITY_RESULT_DEF = """type: ScriptExecutionResultValueMapProvider
id: identityCompareResult
displayName: Verify Identity - Comparison Result
properties:
  namespaceConfig:
    ref: identityCompareNamespace"""

IDENTITY_UI = """- type: SelfServiceUi
  id: identityVerificationUi
  displayName: Verify Identity UI
  properties:
    cancellationTarget:
      ref: redirectToAuth
    completionTarget:
      ref: redirectToAuth
    flowId:
      ref: identityVerificationFlowId
    maintenanceMessageUiSettings:
      ref: maintMsgUi
    showConfirmationPage: 'false'"""

IDENTITY_PORTAL = """- type: ApplicationPortalTarget
  id: portalTarget-identity-verification
  displayName: Application Portal Target Verify Identity
  properties:
    identifier: identity-verification
    precondition:
      ref: hasAnySecondFactor
    redirectByAccess: 'false'
    redirectTarget:
      type: SelfServiceFlowRedirectTarget
      id: redirect-identity-verification
      displayName: Portal Redirect Verify Identity
      properties:
        flowId:
          ref: identityVerificationFlowId"""

STEP_UP_APP = """- type: TargetApplication
  id: identityStepUpApp
  displayName: Verify Identity - Step-Up (second factor)
  properties:
    applicationId:
      type: ApplicationId
      id: identityStepUpApplicationId
      displayName: Application ID "identity-step-up"
      properties:
        applicationId: identity-step-up
    applicationSelector:
      type: RegexApplicationSelector
      id: identityStepUpSelector
      displayName: Self-Service Flow identity-verification URLs
      properties:
        uriPattern: .*/protected/.*identity-verification.*
    authenticationFlow:
      type: AuthenticationFlow
      id: authFlow-identityStepUp
      displayName: Verify Identity - Step-Up Flow (password if needed, second factor)
      properties:
        steps:
        - pluginList:
          - ref: adminLocalPwdStep
          - type: SelectionStep
            id: identityStepUpFactorStep
            displayName: Second Factor Selection (verify identity step-up)
            properties:
              stepId:
                type: StepId
                id: identityStepUpFactorStepId
                displayName: Verify Identity Step-Up Step ID "identity-step-up-second-factor"
                properties:
                  id: identity-step-up-second-factor
              availableOptions:
              - pluginList:
                - ref: mainFidoSelectionOption
                - ref: mainAirlock2faSelectionOption
                - ref: oathOtpSelectionOption
                - ref: emailOtpSelectionOption
              skipCondition:
                ref: hasStrongAuthTag"""

STEP_UP_UI = """- type: AuthenticationUi
  id: identityStepUpUi
  displayName: Verify Identity - Step-Up UI
  properties:
    cancellationTarget:
      ref: sameFlowRedirectTarget
    maintenanceMessageUiSettings:
      ref: maintMsgUi
    targetApplicationId:
      ref: identityStepUpApplicationId
    targetURIResolver:
      ref: portalPageRedirectTarget"""

GENERATED = ['identityVerificationFlow', 'identityVerificationUi', 'portalTarget-identity-verification',
             'identityStepUpApp', 'identityStepUpUi']
