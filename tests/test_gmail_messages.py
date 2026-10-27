import base64

from email_assistant.gmail.messages import to_email


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_prefers_plain_text_part():
    message = {"payload": {
        "headers": [{"name": "From", "value": "A <a@x.com>"}, {"name": "To", "value": "me@x.com"},
                    {"name": "Subject", "value": "Hello"}],
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _b64("plain body")}},
            {"mimeType": "text/html", "body": {"data": _b64("<p>html body</p>")}},
        ],
    }}
    email = to_email(message)
    assert email == {"author": "A <a@x.com>", "to": "me@x.com", "subject": "Hello", "email_thread": "plain body",
                     "folder": "inbox"}


def test_falls_back_to_html_as_text():
    message = {"payload": {"headers": [], "mimeType": "text/html",
                           "body": {"data": _b64("<style>x{}</style><p>Hi&amp;bye</p><br>next")}}}
    assert to_email(message)["email_thread"] == "Hi&bye\n\nnext"


def test_plain_part_drops_mso_conditional_comments():
    plain = "Hi there\r\n\r\n<!--[if !mso]><!-->\r\n\r\n<!--[if false]><!-->\r\n\r\n\r\nSee you\r\n<!--<![endif]-->"
    message = {"payload": {"headers": [], "mimeType": "text/plain", "body": {"data": _b64(plain)}}}
    assert to_email(message)["email_thread"] == "Hi there\n\nSee you"


def test_escaped_markup_is_not_reintroduced_by_unescaping():
    plain = "Hello &lt;!--[if mso]&gt;hidden&lt;![endif]--&gt; &lt;b&gt;world&lt;/b&gt; &amp; more"
    message = {"payload": {"headers": [], "mimeType": "text/plain", "body": {"data": _b64(plain)}}}
    assert to_email(message)["email_thread"] == "Hello world & more"


def test_html_drops_head_comments_and_preheader_padding():
    markup = ("<!DOCTYPE html><html><head><title>T</title><style>p{}</style></head><body>"
              "<!--[if mso]><table><tr><td>outlook only</td></tr></table><![endif]-->"
              "<div>Offer͏ ‌ ﻿͏ ‌</div><p>Details</p></body></html>")
    message = {"payload": {"headers": [], "mimeType": "text/html", "body": {"data": _b64(markup)}}}
    assert to_email(message)["email_thread"] == "Offer\nDetails"


def test_spam_label_sets_the_folder():
    message = {"labelIds": ["SPAM", "UNREAD"], "payload": {"headers": [], "mimeType": "text/plain",
                                                           "body": {"data": _b64("hi")}}}
    assert to_email(message)["folder"] == "spam"
