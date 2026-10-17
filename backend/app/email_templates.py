"""Localized, branded HTML and text bodies for transactional email."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    text: str
    html: str


# Each entry is subject, heading, introduction, detail, CTA label, footer note.
_COPY: dict[str, dict[str, tuple[str, str, str, str, str, str]]] = {
    "en": {
        "magic_link": (
            "Your Contestmaster sign-in link",
            "Sign in to Contestmaster",
            "Use this one-time link to verify your email address and sign in.",
            "This link expires in 15 minutes and can be used only once.",
            "Verify and sign in",
            "If you did not request this message, you can ignore it.",
        ),
        "guest_verify": (
            "Verify access to your Contestmaster log",
            "Verify your log email",
            "Confirm this address to enable the guest log options you selected.",
            "This link expires in 24 hours and can be used only once.",
            "Verify email address",
            "If you did not request this message, you can ignore it.",
        ),
        "result_notice": (
            "{contest_name}: results are published",
            "Contest results are published",
            "Contestmaster has published result list {publication_number} for {contest_name}.",
            "Open the public results page to view the standings.",
            "View results",
            "You received this because you opted in to result notifications.",
        ),
        "password_reset": (
            "Reset your Contestmaster password",
            "Reset your password",
            "Use this one-time link to reset your Contestmaster password.",
            "This link expires in 30 minutes and can be used only once.",
            "Reset password",
            "If you did not request this message, you can ignore it.",
        ),
        "email_change_current": (
            "Confirm your Contestmaster email change",
            "Confirm your email change",
            "Confirm this email change from your current address.",
            "This link expires in 24 hours and can be used only once.",
            "Confirm email change",
            "If you did not request this message, you can ignore it.",
        ),
        "email_change_new": (
            "Confirm your new Contestmaster email",
            "Confirm your new email",
            "Confirm this address to complete your Contestmaster email change.",
            "This link expires in 24 hours and can be used only once.",
            "Confirm new address",
            "If you did not request this message, you can ignore it.",
        ),
        "generic": (
            "{subject}",
            "{subject}",
            "{explanation}",
            "Use the link below to continue.",
            "Continue",
            "If you did not request this message, you can ignore it.",
        ),
    },
    "de": {
        "magic_link": (
            "Dein Contestmaster-Anmeldelink",
            "Bei Contestmaster anmelden",
            "Mit diesem einmaligen Link bestätigst du deine E-Mail-Adresse und meldest dich an.",
            "Der Link ist 15 Minuten gültig und kann nur einmal verwendet werden.",
            "E-Mail bestätigen und anmelden",
            "Falls du diese Nachricht nicht angefordert hast, kannst du sie ignorieren.",
        ),
        "guest_verify": (
            "Zugriff auf dein Contestmaster-Log bestätigen",
            "E-Mail für dein Log bestätigen",
            "Bestätige diese Adresse, um die ausgewählten Optionen für dein Gast-Log "
            "zu aktivieren.",
            "Der Link ist 24 Stunden gültig und kann nur einmal verwendet werden.",
            "E-Mail-Adresse bestätigen",
            "Falls du diese Nachricht nicht angefordert hast, kannst du sie ignorieren.",
        ),
        "result_notice": (
            "{contest_name}: Ergebnisse veröffentlicht",
            "Wettbewerbsergebnisse veröffentlicht",
            "Contestmaster hat Ergebnisliste {publication_number} für {contest_name} "
            "veröffentlicht.",
            "Öffne die öffentliche Ergebnisseite, um die Platzierungen anzusehen.",
            "Ergebnisse ansehen",
            "Du erhältst diese Nachricht, weil du Ergebnisbenachrichtigungen aktiviert hast.",
        ),
        "password_reset": (
            "Contestmaster-Passwort zurücksetzen",
            "Passwort zurücksetzen",
            "Mit diesem einmaligen Link kannst du dein Contestmaster-Passwort zurücksetzen.",
            "Der Link ist 30 Minuten gültig und kann nur einmal verwendet werden.",
            "Passwort zurücksetzen",
            "Falls du diese Nachricht nicht angefordert hast, kannst du sie ignorieren.",
        ),
        "email_change_current": (
            "Änderung deiner Contestmaster-E-Mail bestätigen",
            "E-Mail-Änderung bestätigen",
            "Bestätige die Änderung von deiner bisherigen E-Mail-Adresse aus.",
            "Der Link ist 24 Stunden gültig und kann nur einmal verwendet werden.",
            "E-Mail-Änderung bestätigen",
            "Falls du diese Nachricht nicht angefordert hast, kannst du sie ignorieren.",
        ),
        "email_change_new": (
            "Neue Contestmaster-E-Mail bestätigen",
            "Neue E-Mail-Adresse bestätigen",
            "Bestätige diese Adresse, um deine E-Mail-Adresse bei Contestmaster zu ändern.",
            "Der Link ist 24 Stunden gültig und kann nur einmal verwendet werden.",
            "Neue Adresse bestätigen",
            "Falls du diese Nachricht nicht angefordert hast, kannst du sie ignorieren.",
        ),
        "generic": (
            "{subject}",
            "{subject}",
            "{explanation}",
            "Verwende den folgenden Link, um fortzufahren.",
            "Weiter",
            "Falls du diese Nachricht nicht angefordert hast, kannst du sie ignorieren.",
        ),
    },
    "fr": {
        "magic_link": (
            "Votre lien de connexion Contestmaster",
            "Se connecter à Contestmaster",
            "Utilisez ce lien à usage unique pour vérifier votre adresse e-mail et vous connecter.",
            "Ce lien expire dans 15 minutes et ne peut être utilisé qu'une seule fois.",
            "Vérifier et se connecter",
            "Si vous n'avez pas demandé ce message, vous pouvez l'ignorer.",
        ),
        "guest_verify": (
            "Vérifiez l'accès à votre journal Contestmaster",
            "Vérifiez l'e-mail de votre journal",
            "Confirmez cette adresse pour activer les options choisies pour votre journal invité.",
            "Ce lien expire dans 24 heures et ne peut être utilisé qu'une seule fois.",
            "Vérifier l'adresse e-mail",
            "Si vous n'avez pas demandé ce message, vous pouvez l'ignorer.",
        ),
        "result_notice": (
            "{contest_name} : résultats publiés",
            "Les résultats du concours sont publiés",
            "Contestmaster a publié la liste de résultats {publication_number} pour "
            "{contest_name}.",
            "Ouvrez la page publique des résultats pour consulter le classement.",
            "Voir les résultats",
            "Vous recevez ce message car vous avez activé les notifications de résultats.",
        ),
        "password_reset": (
            "Réinitialiser votre mot de passe Contestmaster",
            "Réinitialiser votre mot de passe",
            "Utilisez ce lien à usage unique pour réinitialiser votre mot de passe Contestmaster.",
            "Ce lien expire dans 30 minutes et ne peut être utilisé qu'une seule fois.",
            "Réinitialiser le mot de passe",
            "Si vous n'avez pas demandé ce message, vous pouvez l'ignorer.",
        ),
        "email_change_current": (
            "Confirmez le changement d'e-mail Contestmaster",
            "Confirmez le changement d'e-mail",
            "Confirmez ce changement depuis votre adresse actuelle.",
            "Ce lien expire dans 24 heures et ne peut être utilisé qu'une seule fois.",
            "Confirmer le changement",
            "Si vous n'avez pas demandé ce message, vous pouvez l'ignorer.",
        ),
        "email_change_new": (
            "Confirmez votre nouvel e-mail Contestmaster",
            "Confirmez votre nouvelle adresse",
            "Confirmez cette adresse pour terminer le changement d'e-mail Contestmaster.",
            "Ce lien expire dans 24 heures et ne peut être utilisé qu'une seule fois.",
            "Confirmer la nouvelle adresse",
            "Si vous n'avez pas demandé ce message, vous pouvez l'ignorer.",
        ),
        "generic": (
            "{subject}",
            "{subject}",
            "{explanation}",
            "Utilisez le lien ci-dessous pour continuer.",
            "Continuer",
            "Si vous n'avez pas demandé ce message, vous pouvez l'ignorer.",
        ),
    },
    "es": {
        "magic_link": (
            "Tu enlace de acceso a Contestmaster",
            "Accede a Contestmaster",
            "Usa este enlace de un solo uso para verificar tu correo electrónico e iniciar sesión.",
            "El enlace caduca en 15 minutos y solo puede usarse una vez.",
            "Verificar e iniciar sesión",
            "Si no solicitaste este mensaje, puedes ignorarlo.",
        ),
        "guest_verify": (
            "Verifica el acceso a tu registro de Contestmaster",
            "Verifica el correo de tu registro",
            "Confirma esta dirección para activar las opciones seleccionadas para tu "
            "registro de invitado.",
            "El enlace caduca en 24 horas y solo puede usarse una vez.",
            "Verificar correo electrónico",
            "Si no solicitaste este mensaje, puedes ignorarlo.",
        ),
        "result_notice": (
            "{contest_name}: resultados publicados",
            "Se han publicado los resultados",
            "Contestmaster ha publicado la lista de resultados {publication_number} "
            "de {contest_name}.",
            "Abre la página pública de resultados para consultar la clasificación.",
            "Ver resultados",
            "Recibes este mensaje porque activaste las notificaciones de resultados.",
        ),
        "password_reset": (
            "Restablece tu contraseña de Contestmaster",
            "Restablece tu contraseña",
            "Usa este enlace de un solo uso para restablecer tu contraseña de Contestmaster.",
            "El enlace caduca en 30 minutos y solo puede usarse una vez.",
            "Restablecer contraseña",
            "Si no solicitaste este mensaje, puedes ignorarlo.",
        ),
        "email_change_current": (
            "Confirma el cambio de correo de Contestmaster",
            "Confirma el cambio de correo",
            "Confirma este cambio desde tu dirección actual.",
            "El enlace caduca en 24 horas y solo puede usarse una vez.",
            "Confirmar cambio",
            "Si no solicitaste este mensaje, puedes ignorarlo.",
        ),
        "email_change_new": (
            "Confirma tu nuevo correo de Contestmaster",
            "Confirma tu nueva dirección",
            "Confirma esta dirección para completar el cambio de correo de Contestmaster.",
            "El enlace caduca en 24 horas y solo puede usarse una vez.",
            "Confirmar nueva dirección",
            "Si no solicitaste este mensaje, puedes ignorarlo.",
        ),
        "generic": (
            "{subject}",
            "{subject}",
            "{explanation}",
            "Usa el enlace siguiente para continuar.",
            "Continuar",
            "Si no solicitaste este mensaje, puedes ignorarlo.",
        ),
    },
    "it": {
        "magic_link": (
            "Il tuo link di accesso a Contestmaster",
            "Accedi a Contestmaster",
            "Usa questo link monouso per verificare il tuo indirizzo e-mail e accedere.",
            "Il link scade tra 15 minuti e può essere usato una sola volta.",
            "Verifica e accedi",
            "Se non hai richiesto questo messaggio, puoi ignorarlo.",
        ),
        "guest_verify": (
            "Verifica l'accesso al tuo log Contestmaster",
            "Verifica l'e-mail del tuo log",
            "Conferma questo indirizzo per attivare le opzioni selezionate per il tuo log ospite.",
            "Il link scade tra 24 ore e può essere usato una sola volta.",
            "Verifica indirizzo e-mail",
            "Se non hai richiesto questo messaggio, puoi ignorarlo.",
        ),
        "result_notice": (
            "{contest_name}: risultati pubblicati",
            "I risultati del contest sono pubblicati",
            "Contestmaster ha pubblicato la lista dei risultati {publication_number} "
            "per {contest_name}.",
            "Apri la pagina pubblica dei risultati per vedere la classifica.",
            "Visualizza risultati",
            "Ricevi questo messaggio perché hai attivato le notifiche dei risultati.",
        ),
        "password_reset": (
            "Reimposta la password Contestmaster",
            "Reimposta la password",
            "Usa questo link monouso per reimpostare la password Contestmaster.",
            "Il link scade tra 30 minuti e può essere usato una sola volta.",
            "Reimposta password",
            "Se non hai richiesto questo messaggio, puoi ignorarlo.",
        ),
        "email_change_current": (
            "Conferma la modifica dell'e-mail Contestmaster",
            "Conferma la modifica dell'e-mail",
            "Conferma questa modifica dal tuo indirizzo attuale.",
            "Il link scade tra 24 ore e può essere usato una sola volta.",
            "Conferma modifica",
            "Se non hai richiesto questo messaggio, puoi ignorarlo.",
        ),
        "email_change_new": (
            "Conferma la nuova e-mail Contestmaster",
            "Conferma il nuovo indirizzo",
            "Conferma questo indirizzo per completare la modifica dell'e-mail Contestmaster.",
            "Il link scade tra 24 ore e può essere usato una sola volta.",
            "Conferma nuovo indirizzo",
            "Se non hai richiesto questo messaggio, puoi ignorarlo.",
        ),
        "generic": (
            "{subject}",
            "{subject}",
            "{explanation}",
            "Usa il link seguente per continuare.",
            "Continua",
            "Se non hai richiesto questo messaggio, puoi ignorarlo.",
        ),
    },
}

_BRAND_TAGLINE = {
    "en": "Amateur radio contest engine",
    "de": "Plattform für Amateurfunkwettbewerbe",
    "fr": "Plateforme de concours radioamateur",
    "es": "Plataforma de concursos de radioafición",
    "it": "Piattaforma per contest radioamatoriali",
}


def render_email(
    template: str,
    *,
    locale: str,
    link: str | None,
    values: dict[str, str | int] | None = None,
) -> RenderedEmail:
    language = locale if locale in _COPY else "en"
    fields = _COPY[language].get(template, _COPY[language]["generic"])
    substitutions = values or {}
    subject, heading, intro, detail, button, footer = (
        item.format_map(_SafeFormat(substitutions)) for item in fields
    )
    escaped_link = escape(link or "", quote=True)
    escaped_heading = escape(heading)
    escaped_intro = escape(intro)
    escaped_detail = escape(detail)
    escaped_footer = escape(footer)
    escaped_button = escape(button)
    escaped_tagline = escape(_BRAND_TAGLINE[language])
    visible_link = link or ""
    text_parts = [heading, intro, detail]
    if visible_link:
        text_parts.extend([button + ":", visible_link])
    text_parts.append(footer)
    text_body = "\n\n".join(part for part in text_parts if part)
    action_html = (
        f'<p style="margin:28px 0 18px"><a href="{escaped_link}" '
        'style="display:inline-block;background:#7d292b;color:#fffdfa;text-decoration:none;'
        'font-weight:700;padding:13px 20px;border-radius:5px">'
        f'{escaped_button}</a></p><p style="font-size:13px;line-height:1.5;word-break:break-all;">'
        f'<a href="{escaped_link}" style="color:#652629">{escape(visible_link)}</a></p>'
        if link
        else ""
    )
    html_body = (
        f'<!doctype html><html lang="{language}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        '<body style="margin:0;padding:28px 12px;background:#f7f0ec;color:#282421;'
        'font-family:Arial,Helvetica,sans-serif">'
        '<div style="max-width:600px;margin:0 auto;background:#fffdfa;border:1px solid #ded2c9;'
        'border-radius:8px;overflow:hidden">'
        '<div style="padding:22px 28px;background:#511e20;color:#f9eeeb;'
        'border-bottom:5px solid #ce6a54">'
        '<div style="font-size:23px;font-weight:700;letter-spacing:.2px">Contestmaster</div>'
        '<div style="margin-top:4px;color:#f0dad5;font-size:13px">'
        f"{escaped_tagline}</div></div>"
        '<div style="padding:30px 28px 24px">'
        f'<h1 style="margin:0 0 18px;color:#511e20;font-size:24px;'
        f'line-height:1.25">{escaped_heading}</h1>'
        f'<p style="margin:0 0 14px;font-size:16px;line-height:1.6">{escaped_intro}</p>'
        f'<p style="margin:0;color:#655b55;font-size:14px;line-height:1.6">{escaped_detail}</p>'
        f'{action_html}</div><div style="padding:16px 28px;background:#f8ece7;'
        "border-top:1px solid #c69d91;"
        f'color:#655b55;font-size:12px;line-height:1.5">{escaped_footer}</div></div>'
        '<div style="max-width:600px;margin:12px auto 0;text-align:center;'
        'color:#655b55;font-size:11px">'
        f"Contestmaster · {escaped_tagline}</div></body></html>"
    )
    return RenderedEmail(subject=subject, text=text_body, html=html_body)


class _SafeFormat(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
