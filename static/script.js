/* ===================================================================
   REAL ESTATE - Property Management
   -------------------------------------------------------------------
   PART A - Effect system (deep space / aurora / cursor / glass)
   PART B - Dashboard behaviour (toasts, search, delete dialog, preview)

   The effect classes and keyframes all live in static/style.css
   (.sparkle, .sparkle-star, .sonar-ping, .mouse-glow-element,
   .mouse-near, .mouse-over, .char-scatter, sparkleFade,
   sparkleStarAnim, sonarExpand ...). This file only drives them.

   Elements this file creates itself (particle canvas, orbs, cursor
   glow, mouse trail) are styled inline here, which is how the original
   effect layer worked - they are not part of the stylesheet's design
   system, they are the atmosphere behind it.
   =================================================================== */
(function () {
    'use strict';

    /* ===============================================================
       ENVIRONMENT
       Mouse-driven effects only run for a real pointer. Ambient
       atmosphere still runs on touch, as long as motion is allowed.
       =============================================================== */

    function mq(query) {
        return window.matchMedia && window.matchMedia(query).matches;
    }

    var reduceMotion = mq('(prefers-reduced-motion: reduce)');
    var finePointer = mq('(hover: hover) and (pointer: fine)');
    var lowPower = (navigator.hardwareConcurrency || 8) <= 4 ||
                   (navigator.deviceMemory || 8) <= 4 ||
                   window.innerWidth < 720;

    var ambientFx = !reduceMotion;              // background atmosphere
    var pointerFx = finePointer && !reduceMotion; // anything driven by the mouse

    document.addEventListener('DOMContentLoaded', function () {
        /* ---- Part A: atmosphere ---- */
        if (ambientFx) {
            initParticleCanvas();
            initFloatingOrbs();
        }
        /* ---- Part A: pointer-driven ---- */
        if (pointerFx) {
            initMouseParallax();
            initCursorGlow();
            initMouseTrailShapes();
            initSparkleOnHover();
            initSonarPingOnClick();
            initCardTilt();
            initMouseProximityGlow();
            initBrandGravity();
            initMagneticButtons();
            initMorphingAvatars();
            initTextWaveOnHover();
            initNavLinkEffects();
            initSubmissionHoverFx();
            initElementMouseEnterFx();
        }
        /* ---- Part A: safe on every device ---- */
        initRippleEffect();
        initElectricInputs();
        initSmoothFormLabels();
        if (!reduceMotion) {
            initScrollReveal();
            initTypingEffect();
            initCountUpBadges();
        }

        /* ---- Part B: dashboard behaviour ---- */
        initToasts();
        initSearch();
        initDeleteDialog();
        initLivePreview();
        initImageUrlManager();
        initPropertyGallery();

        if (pointerFx) {
            startFrameLoop();
        }
    });


    /* ===============================================================
       SHARED POINTER + FRAME LOOP
       The original bound a separate mousemove handler per effect. The
       visual result is identical, but here every per-frame effect
       shares one passive listener and one requestAnimationFrame loop,
       and the loop stops completely while the tab is hidden.
       =============================================================== */

    var pointer = { x: -9999, y: -9999, px: -9999, py: -9999, inside: false };
    var frameTasks = [];
    var frameHandle = null;

    document.addEventListener('mousemove', function (event) {
        pointer.x = event.clientX;
        pointer.y = event.clientY;
        pointer.px = event.pageX;
        pointer.py = event.pageY;
        pointer.inside = true;
    }, { passive: true });

    document.addEventListener('mouseleave', function () {
        pointer.inside = false;
    });

    function onFrame(task) {
        frameTasks.push(task);
    }

    function tick() {
        for (var i = 0; i < frameTasks.length; i++) {
            frameTasks[i]();
        }
        frameHandle = window.requestAnimationFrame(tick);
    }

    function startFrameLoop() {
        if (frameHandle === null && frameTasks.length) {
            frameHandle = window.requestAnimationFrame(tick);
        }
    }

    function stopFrameLoop() {
        if (frameHandle !== null) {
            window.cancelAnimationFrame(frameHandle);
            frameHandle = null;
        }
    }

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            stopFrameLoop();
        } else if (pointerFx) {
            startFrameLoop();
        }
    });

    /* A fixed, click-through layer that holds the atmosphere.
       position:fixed keeps it out of the body's flex flow. */
    var fxLayer = null;
    var bgLayer = null;

    function layer() {
        if (!fxLayer) {
            fxLayer = document.createElement('div');
            fxLayer.setAttribute('aria-hidden', 'true');
            fxLayer.style.cssText =
                'position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden;';
            document.body.prepend(fxLayer);
        }
        return fxLayer;
    }

    /* Parallax lives on its own inner layer. A transform makes an element the
       containing block for position:fixed descendants, so the cursor glow and
       trail must stay outside anything that gets transformed. */
    function background() {
        if (!bgLayer) {
            bgLayer = document.createElement('div');
            bgLayer.style.cssText = 'position:absolute;inset:0;will-change:transform;';
            layer().appendChild(bgLayer);
        }
        return bgLayer;
    }

    /* The controls that receive the click ripple. The sonar ping stands down
       on these, so a button gets one deliberate ripple instead of a ripple,
       a sonar ring and a CSS circle all expanding from the same pixel.
       Everywhere else on the page - rows, cards, the background - the sonar
       is untouched. */
    var RIPPLE_TARGETS =
        '.btn-submit, .input-group button, .btn-icon, .nav-link, ' +
        '.btn-link-primary, .btn-link-secondary';

    var PALETTE = [
        'rgba(124, 92, 252, ',   // --accent
        'rgba(0, 245, 255, ',    // --neon-cyan
        'rgba(255, 0, 170, ',    // --neon-pink
        'rgba(177, 78, 255, '    // --neon-purple
    ];


    /* ===============================================================
       1. PARTICLE CANVAS - stars + constellation
       A second particle layer on top of the CSS star field in
       style.css (body::after), giving the background real depth:
       drifting stars, lines between near neighbours, and a cursor
       that pushes them around.
       =============================================================== */

    function initParticleCanvas() {
        var canvas = document.createElement('canvas');
        canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;';
        background().appendChild(canvas);

        var ctx = canvas.getContext('2d');
        var dpr = Math.min(window.devicePixelRatio || 1, 2);
        var particles = [];
        var w = 0;
        var h = 0;

        function resize() {
            w = window.innerWidth;
            h = window.innerHeight;
            canvas.width = Math.floor(w * dpr);
            canvas.height = Math.floor(h * dpr);
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            build();
        }

        function build() {
            var target = Math.round((w * h) / (lowPower ? 26000 : 13000));
            target = Math.max(18, Math.min(target, lowPower ? 40 : 90));
            particles = [];
            for (var i = 0; i < target; i++) {
                particles.push({
                    x: Math.random() * w,
                    y: Math.random() * h,
                    vx: (Math.random() - 0.5) * 0.28,
                    vy: (Math.random() - 0.5) * 0.28,
                    r: 0.6 + Math.random() * 1.4,
                    a: 0.25 + Math.random() * 0.45,
                    c: PALETTE[i % PALETTE.length]
                });
            }
        }

        var resizeTimer = null;
        window.addEventListener('resize', function () {
            window.clearTimeout(resizeTimer);
            resizeTimer = window.setTimeout(resize, 200);
        });

        resize();

        var LINK = lowPower ? 96 : 132;
        var REACH = 150;

        function draw() {
            ctx.clearRect(0, 0, w, h);

            var i, j, p, q, dx, dy, dist;

            for (i = 0; i < particles.length; i++) {
                p = particles[i];

                p.x += p.vx;
                p.y += p.vy;

                // wrap softly at the edges
                if (p.x < -10) { p.x = w + 10; }
                if (p.x > w + 10) { p.x = -10; }
                if (p.y < -10) { p.y = h + 10; }
                if (p.y > h + 10) { p.y = -10; }

                // the cursor gently pushes nearby stars away
                if (pointer.inside) {
                    dx = p.x - pointer.x;
                    dy = p.y - pointer.y;
                    dist = Math.sqrt(dx * dx + dy * dy);
                    if (dist < REACH && dist > 0.1) {
                        var push = (REACH - dist) / REACH * 0.6;
                        p.x += (dx / dist) * push;
                        p.y += (dy / dist) * push;
                    }
                }

                ctx.beginPath();
                ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                ctx.fillStyle = p.c + p.a + ')';
                ctx.fill();
            }

            // constellation lines between near neighbours
            ctx.lineWidth = 1;
            for (i = 0; i < particles.length; i++) {
                p = particles[i];
                for (j = i + 1; j < particles.length; j++) {
                    q = particles[j];
                    dx = p.x - q.x;
                    dy = p.y - q.y;
                    if (dx > LINK || dx < -LINK || dy > LINK || dy < -LINK) {
                        continue;
                    }
                    dist = Math.sqrt(dx * dx + dy * dy);
                    if (dist < LINK) {
                        ctx.beginPath();
                        ctx.moveTo(p.x, p.y);
                        ctx.lineTo(q.x, q.y);
                        ctx.strokeStyle = 'rgba(124, 92, 252, ' +
                            (0.14 * (1 - dist / LINK)).toFixed(3) + ')';
                        ctx.stroke();
                    }
                }

                // and a brighter thread to the cursor
                if (pointer.inside) {
                    dx = p.x - pointer.x;
                    dy = p.y - pointer.y;
                    dist = Math.sqrt(dx * dx + dy * dy);
                    if (dist < REACH) {
                        ctx.beginPath();
                        ctx.moveTo(p.x, p.y);
                        ctx.lineTo(pointer.x, pointer.y);
                        ctx.strokeStyle = 'rgba(0, 245, 255, ' +
                            (0.20 * (1 - dist / REACH)).toFixed(3) + ')';
                        ctx.stroke();
                    }
                }
            }
        }

        if (pointerFx) {
            onFrame(draw);
        } else {
            // touch / no-pointer: still drift, just on its own slower loop
            var driftHandle = null;
            var drift = function () {
                draw();
                driftHandle = window.requestAnimationFrame(drift);
            };
            driftHandle = window.requestAnimationFrame(drift);
            document.addEventListener('visibilitychange', function () {
                if (document.hidden) {
                    window.cancelAnimationFrame(driftHandle);
                } else {
                    driftHandle = window.requestAnimationFrame(drift);
                }
            });
        }
    }


    /* ===============================================================
       2. FLOATING ORBS
       Restored from the original implementation (five blurred colour
       orbs drifting behind the UI). The original injected a <style>
       block with five random @keyframes; this drives the identical
       motion through the Web Animations API instead, so nothing is
       written into the document and the orbs can be paused.
       =============================================================== */

    var orbAnimations = [];

    function initFloatingOrbs() {
        var orbColors = [
            'rgba(124, 92, 252, 0.08)',
            'rgba(0, 245, 255, 0.06)',
            'rgba(255, 0, 170, 0.05)',
            'rgba(177, 78, 255, 0.06)'
        ];

        var host = document.createElement('div');
        host.style.cssText = 'position:absolute;inset:0;overflow:hidden;';
        background().appendChild(host);

        var count = lowPower ? 3 : 5;

        for (var i = 0; i < count; i++) {
            var orb = document.createElement('div');
            var size = 150 + Math.random() * 200;
            orb.style.cssText =
                'position:absolute;' +
                'width:' + size + 'px;' +
                'height:' + size + 'px;' +
                'border-radius:50%;' +
                'background:radial-gradient(circle, ' + orbColors[i % orbColors.length] + ', transparent 70%);' +
                'left:' + (Math.random() * 100) + '%;' +
                'top:' + (Math.random() * 100) + '%;' +
                'filter:blur(40px);';
            host.appendChild(orb);

            var x1 = (Math.random() - 0.5) * 200;
            var y1 = (Math.random() - 0.5) * 200;
            var x2 = (Math.random() - 0.5) * 200;
            var y2 = (Math.random() - 0.5) * 200;

            if (typeof orb.animate === 'function') {
                orbAnimations.push(orb.animate([
                    { transform: 'translate(0px, 0px) scale(1)' },
                    { transform: 'translate(' + x1 + 'px, ' + y1 + 'px) scale(1.1)', offset: 0.25 },
                    { transform: 'translate(' + x2 + 'px, ' + y2 + 'px) scale(0.9)', offset: 0.5 },
                    { transform: 'translate(' + (-x1) + 'px, ' + (-y2) + 'px) scale(1.05)', offset: 0.75 },
                    { transform: 'translate(0px, 0px) scale(1)' }
                ], {
                    duration: (15 + Math.random() * 15) * 1000,
                    iterations: Infinity,
                    easing: 'ease-in-out'
                }));
            }
        }

        document.addEventListener('visibilitychange', function () {
            orbAnimations.forEach(function (animation) {
                if (document.hidden) {
                    animation.pause();
                } else {
                    animation.play();
                }
            });
        });
    }


    /* ===============================================================
       3. MOUSE PARALLAX
       The atmosphere drifts against the cursor, so the background
       sits behind the glass rather than on it.
       =============================================================== */

    function initMouseParallax() {
        var target = background();
        var cx = 0;
        var cy = 0;

        onFrame(function () {
            var wantX = pointer.inside ? (pointer.x / window.innerWidth - 0.5) * -24 : 0;
            var wantY = pointer.inside ? (pointer.y / window.innerHeight - 0.5) * -24 : 0;
            cx += (wantX - cx) * 0.045;
            cy += (wantY - cy) * 0.045;
            if (Math.abs(wantX - cx) > 0.01 || Math.abs(wantY - cy) > 0.01) {
                target.style.transform = 'translate3d(' + cx.toFixed(2) + 'px,' + cy.toFixed(2) + 'px,0)';
            }
        });
    }


    /* ===============================================================
       4. CURSOR GLOW TRAIL
       A soft light that lags behind the cursor, plus a small cyan
       core that tracks it closely.
       =============================================================== */

    function initCursorGlow() {
        var glow = document.createElement('div');
        glow.style.cssText =
            'position:fixed;top:0;left:0;width:260px;height:260px;margin:-130px 0 0 -130px;' +
            'border-radius:50%;pointer-events:none;z-index:0;opacity:0;' +
            'background:radial-gradient(circle, rgba(124,92,252,0.16), rgba(0,245,255,0.06) 45%, transparent 70%);' +
            'filter:blur(14px);transition:opacity 0.4s ease;will-change:transform;';
        layer().appendChild(glow);

        var dot = document.createElement('div');
        dot.style.cssText =
            'position:fixed;top:0;left:0;width:6px;height:6px;margin:-3px 0 0 -3px;' +
            'border-radius:50%;pointer-events:none;z-index:0;opacity:0;' +
            'background:rgba(0,245,255,0.85);box-shadow:0 0 10px rgba(0,245,255,0.8);' +
            'transition:opacity 0.3s ease;will-change:transform;';
        layer().appendChild(dot);

        var gx = 0, gy = 0, dx = 0, dy = 0;

        onFrame(function () {
            if (!pointer.inside) {
                glow.style.opacity = '0';
                dot.style.opacity = '0';
                return;
            }
            glow.style.opacity = '1';
            dot.style.opacity = '1';

            gx += (pointer.x - gx) * 0.11;
            gy += (pointer.y - gy) * 0.11;
            dx += (pointer.x - dx) * 0.34;
            dy += (pointer.y - dy) * 0.34;

            glow.style.transform = 'translate3d(' + gx.toFixed(1) + 'px,' + gy.toFixed(1) + 'px,0)';
            dot.style.transform = 'translate3d(' + dx.toFixed(1) + 'px,' + dy.toFixed(1) + 'px,0)';
        });
    }


    /* ===============================================================
       5. MOUSE TRAIL
       Small shapes dropped along the cursor path that fade out.
       The original created a fresh node per mousemove; this keeps a
       fixed pool and recycles it, so the trail looks the same but
       never grows the DOM or leaks nodes.
       =============================================================== */

    function initMouseTrailShapes() {
        var POOL = lowPower ? 10 : 18;
        var nodes = [];
        var next = 0;
        var lastX = 0;
        var lastY = 0;

        for (var i = 0; i < POOL; i++) {
            var node = document.createElement('div');
            var cyan = i % 3 === 0;
            var pink = i % 3 === 1;
            var size = cyan ? 5 : (pink ? 4 : 6);
            node.style.cssText =
                'position:fixed;top:0;left:0;pointer-events:none;z-index:0;opacity:0;' +
                'width:' + size + 'px;height:' + size + 'px;' +
                'margin:' + (-size / 2) + 'px 0 0 ' + (-size / 2) + 'px;' +
                'border-radius:' + (i % 4 === 0 ? '2px' : '50%') + ';' +
                'background:' + (cyan ? 'rgba(0,245,255,0.75)'
                              : pink ? 'rgba(255,0,170,0.65)'
                                     : 'rgba(124,92,252,0.75)') + ';' +
                'box-shadow:0 0 8px currentColor;will-change:transform,opacity;';
            layer().appendChild(node);
            nodes.push(node);
        }

        onFrame(function () {
            if (!pointer.inside) {
                return;
            }
            var mx = pointer.x - lastX;
            var my = pointer.y - lastY;
            // only drop a mark once the cursor has actually travelled
            if (mx * mx + my * my < 90) {
                return;
            }
            lastX = pointer.x;
            lastY = pointer.y;

            var node = nodes[next];
            next = (next + 1) % nodes.length;

            node.style.transform = 'translate3d(' + pointer.x + 'px,' + pointer.y + 'px,0) scale(1)';

            if (typeof node.animate === 'function') {
                node.animate([
                    { opacity: 0.85, transform: node.style.transform },
                    {
                        opacity: 0,
                        transform: 'translate3d(' + pointer.x + 'px,' + (pointer.y + 14) + 'px,0) scale(0.2)'
                    }
                ], { duration: 620, easing: 'ease-out', fill: 'forwards' });
            }
        });
    }


    /* ===============================================================
       6. SPARKLE BURSTS
       Uses .sparkle and .sparkle-star from style.css (sparkleFade /
       sparkleStarAnim). Fired on entering a real control, so they
       stay a deliberate micro-interaction rather than page noise.
       =============================================================== */

    function initSparkleOnHover() {
        var selector = '.btn-submit, .input-group button, .btn-icon, .user-avatar, ' +
                       '.nav-link, .badge, .btn-link-primary, .btn-link-secondary';

        document.addEventListener('mouseover', function (event) {
            var host = event.target.closest ? event.target.closest(selector) : null;
            if (!host || host.getAttribute('data-sparkling')) {
                return;
            }
            // ignore moves between children of the same control
            if (event.relatedTarget && host.contains(event.relatedTarget)) {
                return;
            }

            host.setAttribute('data-sparkling', '1');
            window.setTimeout(function () {
                host.removeAttribute('data-sparkling');
            }, 420);

            var box = host.getBoundingClientRect();
            var count = 4;

            for (var i = 0; i < count; i++) {
                spawnSparkle(
                    window.pageXOffset + box.left + Math.random() * box.width,
                    window.pageYOffset + box.top + Math.random() * box.height,
                    i % 2 === 0
                );
            }
        });
    }

    function spawnSparkle(pageX, pageY, star) {
        var node = document.createElement('span');
        node.className = star ? 'sparkle-star' : 'sparkle';
        node.setAttribute('aria-hidden', 'true');
        node.style.left = pageX + 'px';
        node.style.top = pageY + 'px';
        document.body.appendChild(node);

        var done = function () {
            if (node.parentNode) {
                node.parentNode.removeChild(node);
            }
        };
        node.addEventListener('animationend', done);
        window.setTimeout(done, 1000);   // fallback so nothing is ever orphaned
    }


    /* ===============================================================
       7. SONAR PING
       Uses .sonar-ping / sonarExpand from style.css. One ring per
       click, at the click point.
       =============================================================== */

    function initSonarPingOnClick() {
        document.addEventListener('click', function (event) {
            if (event.clientX === 0 && event.clientY === 0) {
                return;   // keyboard-triggered click, no location to ping
            }
            if (event.target.closest && event.target.closest(RIPPLE_TARGETS)) {
                return;   // that control gets the ripple instead
            }

            var ring = document.createElement('span');
            ring.className = 'sonar-ping';
            ring.setAttribute('aria-hidden', 'true');
            ring.style.left = event.pageX + 'px';
            ring.style.top = event.pageY + 'px';
            document.body.appendChild(ring);

            var done = function () {
                if (ring.parentNode) {
                    ring.parentNode.removeChild(ring);
                }
            };
            ring.addEventListener('animationend', done);
            window.setTimeout(done, 1000);
        });
    }


    /* ===============================================================
       8. 3D CARD TILT
       The card leans towards the cursor and settles back on leave.
       .card sets `animation: cardSlideUp ... both`, and an animation
       outranks an inline transform - but .card:hover swaps in
       cardInnerPulse, which only animates box-shadow. That is exactly
       why the tilt is free to apply while hovering.
       The delete dialog is a .card too, and its position is set from
       placeDialog(), so it is excluded.
       =============================================================== */

    function tiltTargets() {
        return document.querySelectorAll('.card:not([data-delete-dialog])');
    }

    function initCardTilt() {
        Array.prototype.forEach.call(tiltTargets(), function (card) {
            var frame = null;

            /* The one-time cardSlideUp entrance animation (style.css) has
               to let go of `transform` once it's done, or the next time
               `.card:hover` hands `animation` back to it on mouseleave it
               replays from opacity: 0 instead of just staying put - see
               the .card-settled rule in style.css. */
            card.addEventListener('animationend', function (event) {
                if (event.animationName === 'cardSlideUp') {
                    card.classList.add('card-settled');
                }
            });

            card.addEventListener('mousemove', function (event) {
                if (frame) {
                    return;
                }
                frame = window.requestAnimationFrame(function () {
                    frame = null;
                    var box = card.getBoundingClientRect();
                    var px = (event.clientX - box.left) / box.width - 0.5;
                    var py = (event.clientY - box.top) / box.height - 0.5;
                    card.style.transform =
                        'perspective(900px) rotateX(' + (-py * 5).toFixed(2) + 'deg)' +
                        ' rotateY(' + (px * 5).toFixed(2) + 'deg) translateY(-4px)';
                });
            });

            card.addEventListener('mouseleave', function () {
                if (frame) {
                    window.cancelAnimationFrame(frame);
                    frame = null;
                }
                card.style.transition = 'transform 0.5s cubic-bezier(0.16, 1, 0.3, 1)';
                card.style.transform = '';
                window.setTimeout(function () {
                    card.style.transition = '';
                }, 500);
            });
        });
    }


    /* ===============================================================
       9. MOUSE PROXIMITY GLOW
       Drives .mouse-glow-element / .mouse-near / .mouse-over from
       style.css: the card lights up as the cursor approaches and
       lights up further once it is inside.
       =============================================================== */

    function initMouseProximityGlow() {
        var cards = Array.prototype.slice.call(tiltTargets());
        if (!cards.length) {
            return;
        }

        cards.forEach(function (card) {
            card.classList.add('mouse-glow-element');
        });

        var boxes = [];
        var measure = function () {
            boxes = cards.map(function (card) {
                return card.getBoundingClientRect();
            });
        };
        measure();

        var remeasure = null;
        var scheduleMeasure = function () {
            window.clearTimeout(remeasure);
            remeasure = window.setTimeout(measure, 150);
        };
        window.addEventListener('resize', scheduleMeasure);
        window.addEventListener('scroll', scheduleMeasure, { passive: true });

        var NEAR = 150;

        onFrame(function () {
            if (!pointer.inside) {
                return;
            }
            for (var i = 0; i < cards.length; i++) {
                var box = boxes[i];
                if (!box) {
                    continue;
                }
                var inside = pointer.x >= box.left && pointer.x <= box.right &&
                             pointer.y >= box.top && pointer.y <= box.bottom;

                var dx = Math.max(box.left - pointer.x, 0, pointer.x - box.right);
                var dy = Math.max(box.top - pointer.y, 0, pointer.y - box.bottom);
                var near = !inside && (dx * dx + dy * dy) < NEAR * NEAR;

                var list = cards[i].classList;
                list.toggle('mouse-over', inside);
                list.toggle('mouse-near', near);
            }
        });
    }


    /* ===============================================================
       10. MAGNETIC BUTTONS
       =============================================================== */

    function initMagneticButtons() {
        var buttons = document.querySelectorAll(
            '.btn-submit, .input-group button, .btn-link-primary');

        Array.prototype.forEach.call(buttons, function (btn) {
            btn.addEventListener('mousemove', function (event) {
                var box = btn.getBoundingClientRect();
                var mx = (event.clientX - box.left - box.width / 2) * 0.18;
                var my = (event.clientY - box.top - box.height / 2) * 0.28;
                btn.style.transform = 'translate(' + mx.toFixed(1) + 'px,' +
                    (my - 2).toFixed(1) + 'px) scale(1.03)';
            });

            btn.addEventListener('mouseleave', function () {
                btn.style.transform = '';
            });
        });
    }


    /* ===============================================================
       11. RIPPLE ON CLICK
       =============================================================== */

    function initRippleEffect() {
        document.addEventListener('click', function (event) {
            var btn = event.target.closest ? event.target.closest(RIPPLE_TARGETS) : null;
            if (!btn || reduceMotion) {
                return;
            }

            var box = btn.getBoundingClientRect();
            var size = Math.max(box.width, box.height) * 2;
            var ripple = document.createElement('span');
            ripple.setAttribute('aria-hidden', 'true');
            ripple.style.cssText =
                'position:absolute;border-radius:50%;pointer-events:none;' +
                'background:rgba(255,255,255,0.28);' +
                'width:' + size + 'px;height:' + size + 'px;' +
                'left:' + (event.clientX - box.left - size / 2) + 'px;' +
                'top:' + (event.clientY - box.top - size / 2) + 'px;';

            var previous = window.getComputedStyle(btn).position;
            if (previous === 'static') {
                btn.style.position = 'relative';
            }
            btn.appendChild(ripple);

            if (typeof ripple.animate === 'function') {
                ripple.animate(
                    [{ transform: 'scale(0)', opacity: 0.5 }, { transform: 'scale(1)', opacity: 0 }],
                    { duration: 600, easing: 'ease-out' }
                ).onfinish = function () {
                    if (ripple.parentNode) {
                        ripple.parentNode.removeChild(ripple);
                    }
                };
            } else {
                window.setTimeout(function () {
                    if (ripple.parentNode) {
                        ripple.parentNode.removeChild(ripple);
                    }
                }, 600);
            }
        });
    }


    /* ===============================================================
       12. SCROLL REVEAL
       =============================================================== */

    function initScrollReveal() {
        if (!('IntersectionObserver' in window)) {
            return;
        }

        var items = document.querySelectorAll('.user-item');
        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) {
                    return;
                }
                var el = entry.target;
                observer.unobserve(el);
                // replay the stylesheet's own row entrance
                el.style.animation = 'none';
                void el.offsetWidth;
                el.style.animation = '';
            });
        }, { rootMargin: '0px 0px -40px 0px', threshold: 0.05 });

        Array.prototype.forEach.call(items, function (item, index) {
            if (index > 9) {          // the stylesheet only staggers the first ten
                observer.observe(item);
            }
        });
    }


    /* ===============================================================
       13. TYPING EFFECT for the page subtitle
       =============================================================== */

    function initTypingEffect() {
        var subtitle = document.querySelector('.subtitle');
        if (!subtitle) {
            return;
        }

        var text = subtitle.textContent.trim();
        if (!text || text.length > 120) {
            return;
        }

        subtitle.textContent = '';
        var index = 0;

        window.setTimeout(function step() {
            subtitle.textContent = text.slice(0, index);
            index += 1;
            if (index <= text.length) {
                window.setTimeout(step, 18);
            }
        }, 420);
    }


    /* ===============================================================
       14. COUNT-UP BADGES
       =============================================================== */

    function initCountUpBadges() {
        var badges = document.querySelectorAll('.badge');

        Array.prototype.forEach.call(badges, function (badge) {
            var target = parseInt(badge.textContent, 10);
            if (isNaN(target) || target <= 0) {
                return;
            }

            var started = null;
            var duration = 700;

            var step = function (now) {
                if (started === null) {
                    started = now;
                }
                var progress = Math.min((now - started) / duration, 1);
                badge.textContent = String(Math.round(target * progress));
                if (progress < 1) {
                    window.requestAnimationFrame(step);
                }
            };

            badge.textContent = '0';
            window.requestAnimationFrame(step);
        });
    }


    /* ===============================================================
       15. SMOOTH FORM LABELS
       =============================================================== */

    function initSmoothFormLabels() {
        var fields = document.querySelectorAll('.form-group input, .form-group textarea');

        Array.prototype.forEach.call(fields, function (field) {
            var group = field.closest ? field.closest('.form-group') : null;
            var label = group ? group.querySelector('label') : null;
            if (!label) {
                return;
            }
            field.addEventListener('focus', function () {
                label.style.transform = 'translateX(4px)';
                label.style.color = 'var(--accent-hover)';
            });
            field.addEventListener('blur', function () {
                label.style.transform = '';
                label.style.color = '';
            });
        });
    }


    /* ===============================================================
       16. TEXT WAVE on heading hover  (.char-scatter in style.css)

       The heading paints a gradient on its own box and clips it to the
       text (background-clip: text + transparent text-fill). The glyphs
       carry no colour of their own - they are only a mask for the h1's
       background. A `transform` on a character promotes it to its own
       paint layer: the glyph moves but the h1's clipped gradient does
       not follow, so the character renders empty and disappears.

       The lift therefore uses position/top, which keeps each glyph in
       the heading's normal paint flow where the gradient still covers
       it. Verified: with transforms, 9 of the 18 letters of "Product
       Management" vanished; with top, all 18 stay painted.
       =============================================================== */

    function initTextWaveOnHover() {
        var heading = document.querySelector('h1');
        if (!heading || heading.querySelector('.char-scatter')) {
            return;
        }

        var original = heading.textContent;
        var words = original.split(' ');
        var fragment = document.createDocumentFragment();
        var chars = [];

        words.forEach(function (word, wordIndex) {
            // Real spaces between words stay breakable, and a word can no
            // longer be split apart between two of its own letters.
            if (wordIndex > 0) {
                fragment.appendChild(document.createTextNode(' '));
            }
            if (word === '') {
                return;
            }

            var wordSpan = document.createElement('span');
            wordSpan.style.whiteSpace = 'nowrap';

            for (var i = 0; i < word.length; i++) {
                var span = document.createElement('span');
                span.className = 'char-scatter';
                span.textContent = word.charAt(i);
                span.style.position = 'relative';
                span.style.top = '0px';
                // Neutralises .char-scatter:hover's transform lift, which
                // would blank the letter out and scale it over its neighbours.
                span.style.transform = 'none';
                span.style.transition =
                    'top 0.3s cubic-bezier(0.16, 1, 0.3, 1), color 0.3s ease, text-shadow 0.3s ease';
                wordSpan.appendChild(span);
                chars.push(span);
            }

            fragment.appendChild(wordSpan);
        });

        // Never swap in anything that is not exactly the original heading.
        if (fragment.textContent !== original) {
            return;
        }

        heading.textContent = '';
        heading.appendChild(fragment);

        var timers = [];

        function clearTimers() {
            for (var i = 0; i < timers.length; i++) {
                window.clearTimeout(timers[i]);
            }
            timers = [];
        }

        function settle() {
            for (var i = 0; i < chars.length; i++) {
                chars[i].style.top = '0px';
            }
        }

        heading.addEventListener('mouseenter', function () {
            clearTimers();

            chars.forEach(function (char, index) {
                timers.push(window.setTimeout(function () {
                    char.style.top = '-6px';
                    timers.push(window.setTimeout(function () {
                        char.style.top = '0px';
                    }, 200));
                }, index * 18));
            });

            // However the timers interleave, the wave always ends flat.
            timers.push(window.setTimeout(settle, chars.length * 18 + 400));
        });

        heading.addEventListener('mouseleave', function () {
            clearTimers();
            settle();
        });
    }


    /* ===============================================================
       17. MORPHING AVATARS
       =============================================================== */

    function initMorphingAvatars() {
        document.addEventListener('mouseover', function (event) {
            var avatar = event.target.closest ? event.target.closest('.user-avatar') : null;
            if (!avatar || avatar.getAttribute('data-morphing')) {
                return;
            }
            avatar.setAttribute('data-morphing', '1');
            avatar.style.borderRadius = '38% 62% 55% 45% / 45% 38% 62% 55%';
            window.setTimeout(function () {
                avatar.style.borderRadius = '';
                avatar.removeAttribute('data-morphing');
            }, 600);
        });
    }


    /* ===============================================================
       18. ELECTRIC INPUTS  (electricPulse in style.css)
       =============================================================== */

    function initElectricInputs() {
        var fields = document.querySelectorAll(
            '.form-group input, .form-group textarea, .input-group input, [data-search-input]');

        /* Hover is left entirely to the stylesheet, which already runs
           rainbowBorder on every field and textareaBreathe on the textarea.
           Setting style.animation here overrode that rule wholesale, so the
           textarea's breathing effect could never actually play. Focus still
           layers electricPulse on top of the CSS focusRing. */
        Array.prototype.forEach.call(fields, function (field) {
            field.addEventListener('focus', function () {
                field.style.animation =
                    'focusRing 2s ease-in-out infinite, electricPulse 2s ease-in-out infinite';
            });
            field.addEventListener('blur', function () {
                field.style.animation = '';
            });
        });
    }


    /* ===============================================================
       19. NAV LINK EFFECTS - light follows the cursor across the tab
       =============================================================== */

    function initNavLinkEffects() {
        var links = document.querySelectorAll('.nav-link');

        Array.prototype.forEach.call(links, function (link) {
            link.addEventListener('mousemove', function (event) {
                var box = link.getBoundingClientRect();
                var px = ((event.clientX - box.left) / box.width * 100).toFixed(1);
                link.style.backgroundImage =
                    'radial-gradient(circle at ' + px + '% 50%, rgba(0,245,255,0.14), transparent 60%)';
            });
            link.addEventListener('mouseleave', function () {
                link.style.backgroundImage = '';
            });
        });
    }


    /* ===============================================================
       20. SUBMISSION MESSAGE HOVER - light follows the cursor
       =============================================================== */

    function initSubmissionHoverFx() {
        document.addEventListener('mousemove', function (event) {
            var msg = event.target.closest ? event.target.closest('.submission-message') : null;
            if (!msg) {
                return;
            }
            var box = msg.getBoundingClientRect();
            var px = ((event.clientX - box.left) / box.width * 100).toFixed(1);
            var py = ((event.clientY - box.top) / box.height * 100).toFixed(1);
            msg.style.backgroundImage =
                'radial-gradient(circle at ' + px + '% ' + py + '%, rgba(124,92,252,0.10), transparent 55%)';
        }, { passive: true });

        document.addEventListener('mouseout', function (event) {
            var msg = event.target.closest ? event.target.closest('.submission-message') : null;
            if (msg && !(event.relatedTarget && msg.contains(event.relatedTarget))) {
                msg.style.backgroundImage = '';
            }
        });
    }


    /* ===============================================================
       21. ELEMENT MOUSE-ENTER EFFECTS
       Restored from the original: a soft flash when the cursor enters
       a card, and a breathing pulse on buttons. The original built the
       card flash from an injected @keyframes block; this uses the same
       fade through a transition instead, so nothing is written into
       the document head.
       =============================================================== */

    function initElementMouseEnterFx() {
        Array.prototype.forEach.call(tiltTargets(), function (card) {
            card.addEventListener('mouseenter', function () {
                var flash = document.createElement('span');
                flash.setAttribute('aria-hidden', 'true');
                flash.style.cssText =
                    'position:absolute;inset:0;background:rgba(124,92,252,0.06);' +
                    'pointer-events:none;z-index:1;opacity:0.5;' +
                    'transition:opacity 0.4s ease-out;';
                card.appendChild(flash);

                window.requestAnimationFrame(function () {
                    flash.style.opacity = '0';
                });
                window.setTimeout(function () {
                    if (flash.parentNode) {
                        flash.parentNode.removeChild(flash);
                    }
                }, 450);
            });
        });

        var flashes = document.querySelectorAll('.flash');
        Array.prototype.forEach.call(flashes, function (flash) {
            flash.addEventListener('mouseenter', function () {
                if (flash.getAttribute('data-dismissed')) {
                    return;
                }
                flash.style.animation = 'wobble 0.6s ease';
            });
            flash.addEventListener('animationend', function () {
                if (!flash.getAttribute('data-dismissed')) {
                    flash.style.animation = '';
                }
            });
        });
    }


    /* ===============================================================
       22. BRAND GRAVITY FIELD
       Reproduced exactly from the original wordmark treatment - only
       the text changed (TANTAWY -> REAL ESTATE). The brand behaves
       like a small cosmic object. As the cursor enters its field the
       wordmark and its star icon lean toward it, the existing red glow
       deepens, and the existing galaxy aura swells and carries its
       stars with the cursor.

       Nothing new is drawn: the whole reaction is three custom
       properties written on .brand-aura, and style.css turns them into
       the glow, the swell and the drift. It runs as one more task on
       the shared frame loop, so it adds no listener, no loop, no DOM
       and no particles. It is registered only under pointerFx, so a
       touch device and a reduced-motion visitor never get it, and it
       eases back to exactly zero the moment the cursor leaves.
       =============================================================== */

    function initBrandGravity() {
        var lockup = document.querySelector('.brand-aura');
        if (!lockup) {
            return;
        }

        var REACH = 190;   // how far the field reaches, in px
        var LEAN = 5;      // furthest the wordmark leans, in px

        var box = lockup.getBoundingClientRect();
        var measure = function () {
            box = lockup.getBoundingClientRect();
            // The reach is measured from the centre of the lockup, so it has
            // to grow with the lockup - otherwise the enlarged wordmark eats
            // the whole field and there is nothing left of it outside the
            // letters. At the old wordmark size this still lands on 190.
            REACH = Math.max(190, box.width * 0.60 + 118);
        };
        measure();

        // The lockup rides in on navDrop, so its resting position is not
        // known until that has finished.
        window.setTimeout(measure, 900);

        var remeasure = null;
        var scheduleMeasure = function () {
            window.clearTimeout(remeasure);
            remeasure = window.setTimeout(measure, 150);
        };
        window.addEventListener('resize', scheduleMeasure);
        window.addEventListener('scroll', scheduleMeasure, { passive: true });

        var pull = 0;
        var leanX = 0;
        var leanY = 0;
        var settled = false;

        onFrame(function () {
            var wantPull = 0;
            var wantX = 0;
            var wantY = 0;

            if (pointer.inside) {
                var dx = pointer.x - (box.left + box.width / 2);
                var dy = pointer.y - (box.top + box.height / 2);
                var dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < REACH) {
                    // squared falloff: the field is only really felt up close
                    wantPull = 1 - dist / REACH;
                    wantPull *= wantPull;

                    var away = dist < 1 ? 1 : dist;
                    wantX = (dx / away) * wantPull * LEAN;
                    wantY = (dy / away) * wantPull * LEAN * 0.7;
                }
            }

            pull += (wantPull - pull) * 0.12;
            leanX += (wantX - leanX) * 0.12;
            leanY += (wantY - leanY) * 0.12;

            // Once the field has fully released, write the rest state one
            // last time and then stop touching the DOM completely.
            if (wantPull === 0 && pull < 0.002 &&
                Math.abs(leanX) < 0.02 && Math.abs(leanY) < 0.02) {
                if (settled) {
                    return;
                }
                settled = true;
                pull = 0;
                leanX = 0;
                leanY = 0;
            } else {
                settled = false;
            }

            lockup.style.setProperty('--pull', pull.toFixed(3));
            lockup.style.setProperty('--pull-x', leanX.toFixed(2));
            lockup.style.setProperty('--pull-y', leanY.toFixed(2));
        });
    }

    /* ###############################################################
       PART B - DASHBOARD BEHAVIOUR
       Unchanged from the tested Phase 2 implementation.
       ############################################################### */


    /* ===== Toasts ================================================= */

    function initToasts() {
        var toasts = document.querySelectorAll('[data-toast]');

        Array.prototype.forEach.call(toasts, function (toast, index) {
            var closeButton = toast.querySelector('[data-toast-close]');
            if (closeButton) {
                closeButton.addEventListener('click', function () {
                    dismissToast(toast);
                });
            }
            window.setTimeout(function () {
                dismissToast(toast);
            }, 5000 + index * 500);
        });
    }

    function dismissToast(toast) {
        if (!toast || toast.getAttribute('data-dismissed')) {
            return;
        }
        toast.setAttribute('data-dismissed', 'true');

        if (reduceMotion) {
            toast.remove();
            return;
        }

        // .flash uses animation-fill-mode: both, which would otherwise keep
        // pinning opacity back to 1. Releasing the animation lets it fade.
        toast.style.animation = 'none';
        toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';

        window.requestAnimationFrame(function () {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(-8px)';
        });

        window.setTimeout(function () {
            toast.remove();
        }, 320);
    }


    /* ===== Search ================================================= */

    function initSearch() {
        var input = document.querySelector('[data-search-input]');
        var list = document.querySelector('[data-product-list]');
        if (!input || !list) {
            return;
        }

        var rows = list.querySelectorAll('[data-product]');
        var noResults = document.querySelector('[data-no-results]');
        var counter = document.querySelector('[data-count]');

        function applyFilter() {
            var query = input.value.trim().toLowerCase();
            var visible = 0;

            Array.prototype.forEach.call(rows, function (row) {
                var haystack = row.getAttribute('data-search') || '';
                var match = query === '' || haystack.indexOf(query) !== -1;
                row.hidden = !match;
                if (match) {
                    visible += 1;
                }
            });

            // Only a search with no hits shows this - an empty table has its
            // own separate empty state rendered by Jinja.
            showNoResults(visible === 0);
            if (counter) {
                counter.textContent = String(visible);
            }
        }

        function showNoResults(show) {
            if (!noResults || show === !noResults.hidden) {
                return;
            }
            noResults.hidden = !show;

            if (show) {
                /* .submission-message in style.css fills its entrance
                   animation with `both`, and this block was already
                   display:none when the page first painted - so that
                   animation is parked on frame 0, which means opacity 0.
                   Re-triggering it lets the reveal actually play. */
                noResults.style.animation = 'none';
                void noResults.offsetWidth;
                noResults.style.animation = '';
            }
        }

        input.addEventListener('input', applyFilter);

        input.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && input.value !== '') {
                event.preventDefault();
                input.value = '';
                applyFilter();
            }
        });

        // "/" jumps to the search box, the way most dashboards do.
        document.addEventListener('keydown', function (event) {
            if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) {
                return;
            }
            var active = document.activeElement;
            var tag = active ? active.tagName : '';
            if (tag === 'INPUT' || tag === 'TEXTAREA' || (active && active.isContentEditable)) {
                return;
            }
            event.preventDefault();
            input.focus();
            input.select();
        });
    }


    /* ===== Delete confirmation ==================================== */

    function initDeleteDialog() {
        var dialog = document.querySelector('[data-delete-dialog]');
        var forms = document.querySelectorAll('[data-delete-form]');

        if (!dialog || !forms.length || typeof dialog.showModal !== 'function') {
            return;
        }

        var nameOutput = dialog.querySelector('[data-delete-name]');
        var confirmButton = dialog.querySelector('[data-dialog-confirm]');
        var cancelButton = dialog.querySelector('[data-dialog-cancel]');
        var pendingForm = null;
        var lastFocused = null;

        placeDialog(dialog);

        Array.prototype.forEach.call(forms, function (form) {
            form.addEventListener('submit', function (event) {
                event.preventDefault();
                pendingForm = form;
                lastFocused = document.activeElement;

                if (nameOutput) {
                    // Generic across both delete forms on the site (product
                    // rows and property cards) - whichever page rendered the
                    // form just names what it is deleting.
                    nameOutput.textContent =
                        '“' + (form.getAttribute('data-item-name') || 'this item') + '”';
                }

                openDialog();
                if (cancelButton) {
                    cancelButton.focus();
                }
            });
        });

        if (confirmButton) {
            confirmButton.addEventListener('click', function () {
                if (!pendingForm) {
                    return;
                }
                var form = pendingForm;
                pendingForm = null;
                // form.submit() skips our submit listener, so this really posts.
                closeDialog(function () {
                    form.submit();
                });
            });
        }

        if (cancelButton) {
            cancelButton.addEventListener('click', function () {
                closeDialog();
            });
        }

        // A click landing on the dialog itself came from the backdrop.
        dialog.addEventListener('click', function (event) {
            if (event.target === dialog) {
                closeDialog();
            }
        });

        // Escape - handle it ourselves so the closing animation still plays.
        dialog.addEventListener('cancel', function (event) {
            event.preventDefault();
            closeDialog();
        });

        dialog.addEventListener('close', function () {
            if (lastFocused && typeof lastFocused.focus === 'function') {
                lastFocused.focus();
            }
        });

        function openDialog() {
            // Hand the entrance animation back to style.css (.card / cardSlideUp).
            dialog.style.animation = '';
            dialog.style.transition = '';
            dialog.style.opacity = '';
            dialog.style.transform = '';
            dialog.showModal();
        }

        function closeDialog(afterClose) {
            if (reduceMotion) {
                dialog.close();
                if (afterClose) {
                    afterClose();
                }
                return;
            }

            dialog.style.animation = 'none';
            dialog.style.transition = 'opacity 0.18s ease, transform 0.18s ease';
            dialog.style.opacity = '0';
            dialog.style.transform = 'scale(0.97)';

            window.setTimeout(function () {
                dialog.close();
                if (afterClose) {
                    afterClose();
                }
            }, 180);
        }
    }

    /* style.css starts with `* { margin: 0 }`, which also cancels the
       browser's built-in `dialog { margin: auto }`. Without that margin a
       modal is pinned to the top-left corner, so we restore the geometry
       here - position and size only. Colour, blur, border, radius and the
       entrance animation all still come from the .card rule in style.css. */
    function placeDialog(dialog) {
        dialog.style.position = 'fixed';
        dialog.style.inset = '0';
        dialog.style.margin = 'auto';
        dialog.style.width = 'min(420px, calc(100% - 40px))';
        dialog.style.height = 'fit-content';
    }


    /* ===== Live preview =========================================== */

    /* Generalised over the field set: the product form only ever wired
       name/price/description, the property form wires several more
       (location, property type, listing type, area, bedrooms, bathrooms,
       status). Every field still just declares [data-preview="key"] on
       the input/select and [data-preview-out="key"] on the element that
       should mirror it - same pattern as before, just no longer limited
       to a fixed list of three keys, so this one function drives both
       forms instead of a second preview engine being written for
       properties. "price" and "avatar" keep their special formatting;
       every other key is a plain live text mirror. */
    function initLivePreview() {
        var inputs = document.querySelectorAll('[data-preview]');
        var outputs = document.querySelectorAll('[data-preview-out]');
        if (!inputs.length || !outputs.length) {
            return;
        }

        var fields = {};
        Array.prototype.forEach.call(inputs, function (el) {
            fields[el.getAttribute('data-preview')] = el;
        });

        var outs = {};
        Array.prototype.forEach.call(outputs, function (el) {
            outs[el.getAttribute('data-preview-out')] = el;
        });

        function formatPrice(raw) {
            var amount = parseFloat(String(raw || '').replace(',', '.'));
            if (!isFinite(amount)) {
                return '$0.00';
            }
            return '$' + amount.toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            });
        }

        // A <select>'s live value is its chosen option's label, not its id.
        function valueOf(key) {
            var el = fields[key];
            if (!el) {
                return '';
            }
            if (el.tagName === 'SELECT') {
                var chosen = el.options[el.selectedIndex];
                return chosen ? chosen.textContent.trim() : '';
            }
            return el.value.trim();
        }

        function render() {
            Object.keys(outs).forEach(function (key) {
                var out = outs[key];

                if (key === 'avatar') {
                    var source = valueOf('name') || valueOf('title');
                    out.textContent = source ? source.slice(0, 2).toUpperCase() : '—';
                    return;
                }
                if (key === 'price') {
                    out.textContent = formatPrice(valueOf('price'));
                    return;
                }

                var value = valueOf(key);
                out.textContent = value || out.getAttribute('data-preview-empty') || '';
            });
        }

        Object.keys(fields).forEach(function (key) {
            var el = fields[key];
            el.addEventListener('input', render);
            if (el.tagName === 'SELECT') {
                el.addEventListener('change', render);
            }
        });

        render();
    }


    /* ===== Property image URL manager (Create / Edit property) =====
       Plain add/remove rows for the gallery's URL list - no upload, no
       drag-and-drop, no extra listener class. Every row is just another
       <input name="image_urls"> inside the existing form, so the browser
       submits the whole list the normal way; this only adds and removes
       rows in the DOM. */
    function initImageUrlManager() {
        var manager = document.querySelector('[data-image-manager]');
        if (!manager) {
            return;
        }

        var rowsContainer = manager.querySelector('[data-image-rows]');
        var addButton = manager.querySelector('[data-image-add]');
        var template = manager.querySelector('[data-image-row-template]');
        var maxImages = parseInt(manager.getAttribute('data-max-images'), 10) || 12;

        if (!rowsContainer || !template) {
            return;
        }

        function rows() {
            return rowsContainer.querySelectorAll('[data-image-row]');
        }

        function refreshAddButton() {
            if (addButton) {
                addButton.disabled = rows().length >= maxImages;
            }
        }

        if (addButton) {
            addButton.addEventListener('click', function () {
                if (rows().length >= maxImages) {
                    return;
                }
                rowsContainer.appendChild(template.content.cloneNode(true));
                refreshAddButton();
                var current = rows();
                var input = current[current.length - 1].querySelector('input');
                if (input) {
                    input.focus();
                }
            });
        }

        rowsContainer.addEventListener('click', function (event) {
            var removeButton = event.target.closest ? event.target.closest('[data-image-remove]') : null;
            if (!removeButton) {
                return;
            }
            var row = removeButton.closest ? removeButton.closest('[data-image-row]') : null;
            if (!row) {
                return;
            }

            // Keep at least one row so the field never disappears outright -
            // clearing the single remaining input is enough to submit no URL.
            if (rows().length <= 1) {
                var input = row.querySelector('input');
                if (input) {
                    input.value = '';
                    input.focus();
                }
                return;
            }

            row.remove();
            refreshAddButton();
        });

        refreshAddButton();
    }


    /* ===== Property gallery (Property Details) =====
       Click a thumbnail (or Previous/Next) to swap the main image. Plain
       click handlers - no mousemove listener, no requestAnimationFrame
       loop; every control is a real <button>, so it is already reachable
       and operable from the keyboard without any extra code. Arrow keys
       are added on top as a convenience once a gallery control has focus. */
    function initPropertyGallery() {
        var gallery = document.querySelector('[data-gallery]');
        if (!gallery) {
            return;
        }

        var mainImg = gallery.querySelector('[data-gallery-main-img]');
        var thumbs = gallery.querySelectorAll('[data-gallery-thumb]');
        var prevButton = gallery.querySelector('[data-gallery-prev]');
        var nextButton = gallery.querySelector('[data-gallery-next]');

        if (!mainImg || !thumbs.length) {
            return;
        }

        var index = 0;

        function show(nextIndex) {
            index = (nextIndex + thumbs.length) % thumbs.length;
            var thumb = thumbs[index];

            mainImg.src = thumb.getAttribute('data-src');
            mainImg.alt = thumb.getAttribute('data-alt') || mainImg.alt;

            Array.prototype.forEach.call(thumbs, function (candidate, i) {
                var active = i === index;
                candidate.classList.toggle('active', active);
                candidate.setAttribute('aria-current', active ? 'true' : 'false');
            });
        }

        Array.prototype.forEach.call(thumbs, function (thumb, i) {
            thumb.addEventListener('click', function () {
                show(i);
            });
        });

        if (prevButton) {
            prevButton.addEventListener('click', function () {
                show(index - 1);
            });
        }
        if (nextButton) {
            nextButton.addEventListener('click', function () {
                show(index + 1);
            });
        }

        gallery.addEventListener('keydown', function (event) {
            if (event.key === 'ArrowLeft') {
                event.preventDefault();
                show(index - 1);
            } else if (event.key === 'ArrowRight') {
                event.preventDefault();
                show(index + 1);
            }
        });
    }

}());
