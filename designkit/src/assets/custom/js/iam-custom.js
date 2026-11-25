// Custom extensions of the IAM Loginapp UI (design kit).
// Documentation: https://docs.airlock.com/iam/latest/?topic=IAM-00000023

// Link to the login on the first page of the password reset and the self-registration (the cancel button of the
// later pages also leads to the login: cancellationTarget redirectToAuth). The link starts the login (target
// application demo). Texts (design kit): custom.back-to-login (password reset), custom.registration.back-to-login
// (self-registration: "Already have an account? Log in" - the usual pattern of sign-up pages).
class BackToLoginPage extends iam.api.types.CustomProductPage {
    isApplicable({pageId, stepId}) {
        // password reset (flow password-reset): user identification
        this.registration = stepId === 'userdata';
        // self-registration: user data (step ID userdata, used only there)
        return pageId === 'iamPublicSelfServiceUsername' || this.registration;
    }

    customBlocks() {
        return [
            {
                position: this.customBlockPosition.AFTER_CONTENT,
                html: '<p class="iam-back-to-login"><a href="/auth-login/ui/app/auth/application/access/demo">'
                    + this.translate(this.registration ? 'custom.registration.back-to-login' : 'custom.back-to-login') + '</a></p>'
            }
        ];
    }

    onLanguageChange() {
        this._render();
    }
}

// Times in message texts: <time class="iam-local-time" datetime="<UTC, ISO 8601>">hh:mm UTC</time> (e.g. the end
// of the recovery waiting period) - shown as hh:mm in the browser's time zone. The IAM server only knows UTC.
function showLocalTimes(root) {
    root.querySelectorAll('time.iam-local-time[datetime]').forEach(element => {
        const date = new Date(element.getAttribute('datetime'));
        if (isNaN(date.getTime())) {
            return;
        }
        const text = date.toLocaleTimeString(document.documentElement.lang || undefined, {hour: '2-digit', minute: '2-digit'});
        if (element.textContent !== text) {
            element.textContent = text;
        }
    });
}

// TEMPORARY: "Register as partner admin" button (application adminapp, only in instances with this button) shown but
// disabled. The UI re-enables its buttons after each busy phase, so the attribute is set again whenever it changes.
// To re-enable the button: remove this function and its call in initialize.
function disablePartnerAdminButton(root) {
    const button = root.getElementById('additionalAuthenticationTarget-adminapp');
    if (button && !button.disabled) {
        button.disabled = true;
    }
}

iam.api.customizing.initialize = function () {
    iam.api.customizing.registerPage(new BackToLoginPage());
    // message texts (and buttons) are rendered (and re-rendered on a language change) by the UI at any time
    new MutationObserver(() => {
        showLocalTimes(document);
        disablePartnerAdminButton(document);
    }).observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['disabled']});
};
