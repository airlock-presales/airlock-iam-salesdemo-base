/**
 * A configuration to control the SDK's behavior.
 *
 * For optimal backwards-compatibility, it is highly recommended to only change the properties that are different from the SDK's defaults.
 *
 * The complete documentation can be found here: https://docs.airlock.com/iam/latest/?topic=IAM-00000023.
 *
 * @returns a configuration to be interpreted by the SDK at runtime.
 */
iam.api.sdk.config = function () {
    const config = {
        // Build
        // -----
        // Build settings affect the ZIP artifact and therefore production when it's integrated with Airlock IAM.
        // Other settings are only relevant for development within the SDK.
        build: {
            //     // Disable all CSS styles that are provided by Airlock IAM. This is useful in cases where
            //     // you need full control of the CSS. As a consequence, none of the SASS variables provided
            //     // by the SDK have any effect.
            //     dropStyles: false,
            //
            //     // This mode alters the HTML structure and base style to comply with the specified accessibility standard.
            //     // Affects the UI as shown in the SDK, as well as the resulting ZIP artifact.
            //     // Valid options are: 'legacy', 'wcag'
            //     // 'legacy': Legacy IAM style which partially complies with official accessibility standards (e.g. WCAG)
            //     // 'wcag': Style that fully complies with the Web Content Accessibility Guideline v2.2
            accessibilityMode: 'wcag'
        },

        // Airlock IAM Salesdemo: pages as in the instance, for the dev mode (not part of the zip)
        // ----------------------------------------------------------------------------------------
        pages: [
            // login page (username/password with passkey): additional buttons
            {
                path: '/auth/flow/{{FLOW}}/password/fido',
                pageSettings: {
                    publicSelfServiceLink: '{{SPA}}/self-service/flow/default',
                    userSelfRegistrationLink: '{{SPA}}/registration/flow/default',
                    additionalAuthenticationButtons: {
                        targets: [{applicationId: 'recovery'}, {applicationId: 'usernameless'}, {applicationId: 'adminapp'}]
                    }
                }
            },
            {
                path: '/auth/flow/{{FLOW}}/password',
                pageSettings: {
                    publicSelfServiceLink: '{{SPA}}/self-service/flow/default',
                    userSelfRegistrationLink: '{{SPA}}/registration/flow/default',
                    additionalAuthenticationButtons: {
                        targets: [{applicationId: 'recovery'}, {applicationId: 'usernameless'}, {applicationId: 'adminapp'}]
                    }
                }
            },
            // QR code page (username-less login): button back to the login with username
            {
                path: '/auth/flow/{{FLOW}}/airlock-2fa/usernameless',
                pageSettings: {
                    additionalAuthenticationButtons: {
                        targets: [{applicationId: 'demo'}]
                    }
                }
            },
            // application portal: groups and targets as in the IAM configuration
            {
                path: '/protected/portal',
                pageSettings: {
                    portalGroups: [
                        {
                            identifier: 'iam-administration',
                            portalTargets: [{identifier: 'adminapp'}, {identifier: 'adminer'}, {identifier: 'mailpit'}, {identifier: 'config-restore'}]
                        },
                        {
                            identifier: 'kubernetes-administration',
                            portalTargets: [{identifier: 'argocd'}, {identifier: 'headlamp'}]
                        },
                        {
                            identifier: 'profile-management',
                            portalTargets: [{identifier: 'password-change'}, {identifier: 'name-change'}, {identifier: 'email-address-change'}]
                        },
                        {
                            identifier: 'a2fa-management',
                            portalTargets: [{identifier: 'airlock2fa-device-management'}, {identifier: 'airlock2fa-recovery-info'}]
                        },
                        {
                            identifier: 'mfa-management',
                            portalTargets: [
                                {identifier: 'fido-credential-management'},
                                {identifier: 'oath-otp-activation'},
                                {identifier: 'email-otp-enable'},
                                {identifier: 'email-otp-disable'},
                                {identifier: 'remember-me-device-management'},
                                {identifier: 'preferred-auth-method'}
                            ]
                        }
                    ]
                }
            },
            // set password (configuration-based UI of the partner administrator flow, page ID set-password)
            {
                path: '/auth/flow/{{FLOW}}/ext/set-password',
                uiElements: [
                    {
                        type: 'text',
                        htmlId: 'setPasswordText',
                        text: 'Set the password for logging in to this platform directly.'
                    },
                    {
                        type: 'form',
                        uiElements: [
                            {
                                type: 'input',
                                subtype: 'password',
                                htmlId: 'newPassword',
                                label: 'custom.set-password.new-password',
                                property: 'newPassword'
                            },
                            {
                                type: 'input',
                                subtype: 'password',
                                htmlId: 'confirmPassword',
                                label: 'custom.set-password.confirm-password',
                                property: 'confirmPassword'
                            },
                            {
                                type: 'button',
                                label: 'custom.set-password.submit',
                                htmlId: 'setPasswordButton'
                            }
                        ]
                    }
                ]
            }
        ],

        // the custom page in the dev mode navigation
        navigation: {
            authentication: {
                customUi: [
                    {path: '/auth/flow/{{FLOW}}/ext/set-password'}
                ]
            }
        },

        // Tenant
        // -----
        // Sets the tenant id which is reflected in the data-iam-tenant-id body attribute and used for "isApplicable" API
        // calls on CustomLayout/CustomProductPage/CustomJavaScriptPage.
        // tenantId: 'myTenant',

        // Languages
        // ---------
        // languages: {
        //     // The default language to use if there is no previously selected language or
        //     // the language of the browser cannot be determined.
        //     defaultLanguage: 'de',
        //     // The available languages
        //     availableLanguages: ['de', 'fr', 'it', 'en']
        // },

        // Alerts
        // ------
        // alert: {
        //     // The available i18n keys to choose the alert message from.
        //     // Allowed entries are either strings or objects in the format {key: string, arguments: object}
        //     // where arguments are resolved as placeholders within the translated text.
        //     // The first entry is the default. If no entries are defined, SDK defaults are used.
        //     messages: [
        //         'error.authentication-failed',
        //         {key: 'authentication.pages.messages.remaining-attempts.warning', arguments: {remainingAttempts: '2'}},
        //         'authentication.pages.messages.cancel',
        //         'registration.pages.messages.completed'
        //     ]
        // },

        // Maintenance messages
        // --------------------
        // maintenanceMessage: {
        //     // The maintenance message texts to use
        //     text: {
        //         de: 'Unser System wird in Kürze gewartet und wird in dieser Zeit nicht erreichbar sein.',
        //         en: 'Our system will be serviced shortly and will not be available during this time.',
        //         fr: 'Notre système sera révisé sous peu et ne sera pas disponible pendant cette période.',
        //         it: 'Il nostro sistema verrà sottoposto a manutenzione a breve e non sarà disponibile durante questo periodo.'
        //     }
        // },

        // Buttons
        // -------
        // buttons: {
        //     // Goto buttons
        //     goto: {
        //         // Display a Goto button with corresponding translation key for each step ID
        //         targetStepIds: ['step1', 'step2']
        //     },
        //     // By default, all buttons in the SDK ignore clicks. By setting this property, the HTML IDs
        //     // of buttons that should be made clickable can be defined. This is useful to implement and verify
        //     // the behavior of buttons that were added programmatically using JavaScript, but may lead to
        //     // errors when applied to buttons that are provided by the product.
        //     clickable: []
        // }

        // Checkboxes
        // ----------
        // checkboxes: {
        //     dynamicStepActivation: {
        //         // Display Dynamic Step Activation (DSA) checkboxes with corresponding translation key for each step ID
        //         targetStepIds: ['step1', 'step2']
        //     }
        // },

        // Flows
        // -----
        // flows: {
        //     // The default flow ID to use for all pages. Replaces the {{FLOW}} placeholder in config paths.
        //     defaultFlowId: 'default'
        // },

        // Page Settings
        // -------------
        // pages: [
        //     // Password page
        //     {
        //         path: '/auth/flow/{{FLOW}}/password',
        //         pageSettings: {
        //             // Show public self-service link
        //             publicSelfServiceLink: '{{SPA}}/self-service/flow/default',
        //             // Show self-registration link
        //             userSelfRegistrationLink: '{{SPA}}/registration/flow/default',
        //             additionalAuthenticationButtons: {
        //                 targets: [
        //                     {applicationId: 'applicationId', targetUrl: '{{SPA}}/auth/application/access/applicationId'}
        //                 ]
        //             }
        //         },
        //         validations: [
        //             {
        //                 htmlId: 'username',
        //                 messages: [
        //                     {key: 'error.validation-failed.min-length', arguments: {requiredLength: 6}}
        //                 ]
        //             }
        //         ]
        //     },
        //     // Password change page
        //     {
        //         path: '/auth/flow/{{FLOW}}/password/change',
        //         pageSettings: {
        //             // Whether or not it is necessary to enter the old password
        //             oldPasswordRequired: false
        //         }
        //     },
        //     // Application Portal page
        //     {
        //         path: '/protected/portal',
        //         pageSettings: {
        //             portalGroups: [
        //                 {
        //                     identifier: 'self-services',
        //                     portalTargets: [
        //                         {identifier: 'cronto-device-management'},
        //                         {identifier: 'address-change'},
        //                         {identifier: 'password-change'}
        //                     ]
        //                 },
        //                 {
        //                     identifier: 'custom-group',
        //                     portalTargets: [
        //                         {identifier: 'custom-target'}
        //                     ]
        //                 }
        //             ]
        //         }
        //     }
        // ],

        // Navigation
        // ----------
        // navigation: {
        //     authentication: {
        //         password: [
        //             {path: '/auth/flow/{{FLOW}}/password'},
        //             {path: '/auth/flow/{{FLOW}}/password', stepId: 'my-step-id'},
        //             {path: '/auth/flow/fixed-flow-id/password/change'}
        //         ],
        //         customUi: [
        //             {path: '/auth/flow/{{FLOW}}/ext/my-custom-page'},
        //             {path: '/auth/flow/{{FLOW}}/ext/another-custom-page'}
        //         ]
        //     }
        // },

        // Custom Response Mocking
        // -----------------------------
        // customResponses: [
        //     {
        //         url: '/some/minimal/xhr/example',
        //         response: {
        //             xhr: {
        //                 body: {
        //                     // Your JSON response
        //                 }
        //             }
        //         }
        //     }
        // ],
    };

    return config;
};
