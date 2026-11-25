# shared Lua helpers for the account recovery scripts (inserted into each script)
LUA_LIB = r'''local curl = require "cURL"
local BASE = "http://localhost:8080/auth-admin/rest"

local function urlencode (s)
    return (s:gsub("[^%w%-%._~]", function (c) return string.format("%%%02X", string.byte(c)) end))
end

-- Adminapp REST API (technical administrator selfreg-lookup)
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

local function set_context (user, values)
    call("PATCH", "/users/" .. urlencode(user) .. "/context-data",
        { data = { type = "user.context-data", attributes = values } }, { 200, 204 })
end

local function has_role (user, role)
    for _, r in ipairs(call("GET", "/users/" .. urlencode(user) .. "/roles", nil, { 200 }).data or {}) do
        if r.id == role then return true end
    end
    return false
end

-- contacts of a user for the recovery confirmations: list of { username, email, phone, language }, and
-- whether to notify them
-- - self-registered without responsible administrator (role registration-orphan): options shown,
--   but nobody is asked
-- - responsible administrator set (email entered at the registration): that partner administrator
-- - otherwise: holders of realm role mgr-partners (for partner administrators) or mgr-admins
local function contacts_of (user)
    if has_role(user, "registration-orphan") then return {}, false end
    local ctx = (call("GET", "/users/" .. urlencode(user) .. "/context-data", nil, { 200 }).data or {}).attributes or {}
    local result = {}
    local function add (a)
        local c = ((a.attributes or {}).contextData) or {}
        if a.id ~= user and type(c.email) == "string" and c.email ~= "" then
            local phone = type(c.mtan_number) == "string" and c.mtan_number or ""
            table.insert(result, { username = a.id, email = c.email, phone = phone, language = c.language })
        end
    end
    local responsible = ctx.responsible_admin
    if type(responsible) == "string" and responsible ~= "" then
        local list = call("GET", "/users?caseSensitive=false&page%5Blimit%5D=10&filter="
            .. urlencode("email==" .. responsible), nil, { 200 })
        for _, a in ipairs(list.data or {}) do
            if has_role(a.id, "partner-admin") then add(a); break end
        end
    else
        local wanted = has_role(user, "partner-admin") and "mgr-partners" or "mgr-admins"
        -- the realm filter takes one realm per request
        for _, r in ipairs({ "owners", "partners" }) do
            local list = call("GET", "/users?page%5Blimit%5D=200&filter=" .. urlencode("realm==" .. r), nil, { 200 })
            for _, a in ipairs(list.data or {}) do
                if has_role(a.id, wanted) then add(a) end
            end
        end
    end
    return result, true
end

-- random numeric code
local function new_code (digits)
    local f = io.open("/dev/urandom", "rb")
    local bytes = f:read(digits)
    f:close()
    local code = ""
    for i = 1, digits do code = code .. tostring(string.byte(bytes, i) % 10) end
    return code
end

-- contacts to notify as outputs contact1..contact5 (email addresses) and phone1..phone5 (mobile numbers,
-- context data mtan_number), "" if unused - IAM's email notification steps send the emails (the IAM
-- image's libcurl has no SMTP); with SMS switched on (snippet), an SMS event subscriber texts contacts with
-- a number and their email step is skipped; at most 5 contacts
local MAX_CONTACTS = 5
local function contact_outputs (user, out)
    local contacts, notify = contacts_of(user)
    if not notify then
        iam.log:info("Recovery: " .. user .. " has no contacts to notify (registration-orphan) - nobody asked")
        contacts = {}
    end
    for i = 1, MAX_CONTACTS do
        out["contact" .. i] = contacts[i] and contacts[i].email or ""
        out["phone" .. i] = contacts[i] and contacts[i].phone or ""
    end
    iam.log:info("Recovery: " .. math.min(#contacts, MAX_CONTACTS) .. " of " .. #contacts .. " contact(s) of " .. user .. " notified")
    return out
end
'''
