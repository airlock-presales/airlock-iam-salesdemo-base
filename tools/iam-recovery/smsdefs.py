# mTAN / SMS parts of the account recovery: method "SMS code to the mobile number", SMS switch, settings
#
# SMS switch: off in the template (dummy SMS gateway). An IAM snippet with a real SMS gateway (e.g.
# vmware/iam/snippets/sms-truesenses.yaml) connects smsGateway of recoverySmsSettings and replaces the
# value provider of smsEnabled by a true one (connectPlugin). The mobile number is the context data
# mtan_number (column medusa_user.mtan_number): no mTAN token, so it is no login factor and is not deleted by
# the recovery.
import re

# availability conditions of methods (METHODS "condition extra"), defined at the first use (round 1)
EXTRA_DEFS = {
    'hasEmailAlt': """type: StringRegexCondition
id: hasEmailAlt
displayName: Has Alternate Email Address
properties:
  regexPattern: .+
  valueProvider:
    type: ContextDataStringValueProvider
    id: userEmailAltProvider
    displayName: Existing Alternate Email
    properties:
      contextDataField:
        ref: ctxDataItemNameEmailAlt""",
    'hasMtanNumber': """type: LogicalAndFlowCondition
id: hasMtanNumber
displayName: Has Mobile Number (and SMS switched on)
properties:
  conditions:
  - pluginList:
    - ref: smsEnabled
    - type: StringRegexCondition
      id: hasMtanNumberValue
      displayName: Has Mobile Number (context data mtan_number)
      properties:
        regexPattern: .+
        valueProvider:
          type: ContextDataStringValueProvider
          id: userMtanNumberProvider
          displayName: Existing Mobile Number
          properties:
            contextDataField:
              ref: ctxDataItemNameMtanNumber""",
}

# defined at their first reference (define_first)
SMS_DEFS = {
    'smsEnabled': """type: BooleanCondition
id: smsEnabled
displayName: SMS Switched On (false in the template - an SMS snippet sets it)
properties:
  valueProvider:
    type: BooleanStaticValueProvider
    id: smsSwitchOff
    displayName: SMS Switch - Off (template)
    properties:
      value: 'false'""",
    'recoveryMtanOtpCheck': """type: MtanOtpCheck
id: recoveryMtanOtpCheck
displayName: SMS Code Check (mobile number from context data)
properties:
  basicSettings:
    type: BasicMtanSettings
    id: recoverySmsSettings
    displayName: SMS Settings (gateway - dummy in the template, an SMS snippet connects a real one)
    comment: The mTAN handler is required by the plugin; the steps using these settings get the number from the context data mtan_number (column medusa_user.mtan_number) - no mTAN token, so it is no login factor and not deleted by the recovery.
    properties:
      mtanHandler:
        type: CredentialDataMtanHandler
        id: mtanNumberHandler
        displayName: Mobile Number (column medusa_user.mtan_number)
        properties:
          credentialPersister:
            type: DatabaseCredentialPersister
            id: mtanNumberCredentialPersister
            displayName: Mobile Number on Database
            properties:
              colRecordModificationDate: rowUpdateDate
              colRecordModificationUser: rowUpdateUser
              colStringCredentialData: mtan_number
              colUserName: username
              colVersionId: rowVersionId
              credentialTableName: medusa_user
              sqlDataSource:
                ref: sqlConnection
      originator: Airlock
      smsGateway:
        type: DummySmsGateway
        id: dummySmsGateway
        displayName: Dummy SMS Gateway (writes to the log)
  maxOtpResends: '1'
  maxWrongOtpChecks: '2'
  otpGenerator:
    type: ExtendedStringGenerator
    id: smsOtpGenerator
    displayName: SMS Code Generator (6 digits)
    properties:
      pattern: '{digits:6}'""",
}

MESSAGE_DEF = """type: GenericMtanMessageProvider
id: recoveryMtanMessage
displayName: Recovery - SMS Code Message
properties:
  resourceKey: custom.recovery.sms.code"""


def mtan_step(r):
    """recovery round r: SMS code to the user's mobile number"""
    msg = 'ref: recoveryMtanMessage' if r > 1 else MESSAGE_DEF.replace('\n', '\n      ')
    return f"""- type: MtanVerificationStep
  id: recoveryMtanOtpR{r}
  displayName: Recovery Round {r} - SMS Code to the Mobile Number (1 point)
  properties:
    authenticationMethodId: RECOVERY_MTAN
    iakVerificationRequired: 'false'
    messageProvider:
      {msg}
    mtanSettings:
      ref: recoveryMtanOtpCheck
    phoneNumberProvider:
      ref: userMtanNumberProvider"""


def define_first(t, pid, definition):
    """replace the first reference to pid ('ref: pid' as property or list item) by its definition"""
    m = re.search(r'\n( *)(- )?ref: ' + re.escape(pid) + r'\n', t)
    assert m, pid
    n = len(m.group(1))
    lines = definition.split('\n')
    if m.group(2):
        out = [' ' * n + '- ' + lines[0]] + [(' ' * (n + 2) + l) if l.strip() else l for l in lines[1:]]
    else:
        out = [(' ' * n + l) if l.strip() else l for l in lines]
    return t[:m.start()] + '\n' + '\n'.join(out) + '\n' + t[m.end():]


# self-service "Mobile number": edit, SMS code to the new number, save (context data mtan_number)
MTAN_CHANGE_FLOW = """- type: CustomProtectedSelfServiceFlow
  id: mtanNumberChangeFlow
  displayName: Mobile Number Flow
  comment: Mobile number for the account recovery (context data mtan_number), verified with an SMS code. Only with SMS switched on (SMS snippet).
  properties:
    accessCondition:
      ref: smsEnabled
    flowId:
      type: FlowId
      id: mtanNumberChangeFlowId
      displayName: Flow ID "mtan-number-change"
      properties:
        flowId: mtan-number-change
    steps:
    - pluginList:
      - type: UserDataEditStep
        id: mtanNumberEditStep
        displayName: Mobile Number - Edit
        properties:
          stepId:
            type: StepId
            id: mtanNumberEditStepId
            displayName: Mobile Number Step ID 'edit-mtan-number'
            properties:
              id: edit-mtan-number
          userDataItems:
          - pluginList:
            - type: StringContextDataItemDefinition
              id: mtanNumberItem
              displayName: Mobile Number (input)
              properties:
                contextDataName:
                  ref: ctxDataItemNameMtanNumber
                inputPurpose: tel
                required: 'false'
      - type: MtanVerificationStep
        id: mtanNumberVerifyStep
        displayName: Mobile Number - SMS Code to the New Number
        properties:
          authenticationMethodId: MTAN_NUMBER_CHANGE
          iakVerificationRequired: 'false'
          messageProvider:
            type: GenericMtanMessageProvider
            id: mtanNumberChangeMessage
            displayName: Mobile Number - SMS Code Message
            properties:
              resourceKey: custom.mtan-number.sms.code
          mtanSettings:
            ref: recoveryMtanOtpCheck
          phoneNumberProvider:
            type: StringFromMapValueProvider
            id: mtanNumberEdited
            displayName: Mobile Number - Entered Number
            properties:
              key: mtan_number
              valueMaps:
              - pluginList:
                - ref: recoveryEditedCodeMap
          skipCondition:
            type: LogicalNotFlowCondition
            id: mtanNumberNotEntered
            displayName: Mobile Number - No Number Entered (removed)
            properties:
              condition:
                type: StringRegexCondition
                id: mtanNumberEntered
                displayName: Mobile Number - Number Entered
                properties:
                  regexPattern: .+
                  valueProvider:
                    ref: mtanNumberEdited
      - type: ApplyChangesStep
        id: mtanNumberApply
        displayName: Mobile Number - Save
        properties:
          handlers:
          - pluginList:
            - type: ApplyUserDataEditChange
              id: mtanNumberApplyHandler
              displayName: Apply Mobile Number"""

MTAN_CHANGE_UI = """- type: SelfServiceUi
  id: mtanNumberChangeUi
  displayName: Mobile Number UI
  properties:
    cancellationTarget:
      ref: redirectToAuth
    completionTarget:
      ref: redirectToAuth
    flowId:
      ref: mtanNumberChangeFlowId
    maintenanceMessageUiSettings:
      ref: maintMsgUi
    showConfirmationPage: 'false'"""

MTAN_CHANGE_PORTAL = """- type: ApplicationPortalTarget
  id: portalTarget-mtan-number-change
  displayName: Application Portal Target Mobile Number
  properties:
    identifier: mtan-number-change
    precondition:
      ref: smsEnabled
    redirectByAccess: 'false'
    redirectTarget:
      type: SelfServiceFlowRedirectTarget
      id: redirect-mtan-number-change
      displayName: Portal Redirect Mobile Number
      properties:
        flowId:
          ref: mtanNumberChangeFlowId"""

MTAN_CTX_ITEM = """- type: StringContextDataItem
  id: ctxDataItemMtanNumber
  displayName: Context Data Item 'mtan_number'
  comment: Mobile number of the user (account recovery, SMS), maintained in the self-service "Mobile number" (standard column of medusa_user; not an mTAN token).
  properties:
    contextDataName:
      type: StringContextDataItemName
      id: ctxDataItemNameMtanNumber
      displayName: String Context Data 'mtan_number'
      properties:
        contextDataName: mtan_number"""

MTAN_PROFILE_ITEM = """- type: StringUserProfileItem
  id: mtanNumberLabel
  displayName: Mobile Number Admintool Label
  comment: Also read through the Adminapp REST API by the recovery scripts (SMS to contacts) - REST reads only context data with a user profile item.
  properties:
    propertyName: mtan_number
    stringResourceKey: userdata.label.mtan-number"""
