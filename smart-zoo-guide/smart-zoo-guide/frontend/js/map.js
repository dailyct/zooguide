/* 園區 SVG 地圖。render() 每次都整張重畫，狀態都從 view 參數來，沒有隱藏狀態。 */
const ZooMap = (function () {
    "use strict";

    const NS = "http://www.w3.org/2000/svg";
    const EMOJI = { tiger: "🐯", panda: "🐼", monkey: "🐒", lion: "🦁", elephant: "🐘", penguin: "🐧" };

    function svg(tag, attrs, text) {
        const node = document.createElementNS(NS, tag);
        Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
        if (text !== undefined) node.textContent = text;
        return node;
    }

    /* 路線折線的座標：從起點依序經過每一站；查不到座標的點會被略過。 */
    function routePoints(zones, startId, stopIds) {
        return [startId].concat(stopIds || [])
            .filter(function (id) { return zones[id]; })
            .map(function (id) { return [zones[id].x, zones[id].y]; });
    }

    /*
     * data: /api/route/map 的回應
     * view: { location, visited[], recommended, selected, routeIds[] }
     * onSelect(animalId): 使用者點了某隻動物
     */
    function render(container, data, view, onSelect) {
        const size = data.map || { width: 600, height: 400 };
        const root = svg("svg", {
            viewBox: "0 0 " + size.width + " " + size.height,
            role: "group",
            "aria-label": "園區地圖",
        });

        Object.keys(data.areas || {}).forEach(function (id) {
            const a = data.areas[id];
            root.appendChild(svg("rect", { x: a.x, y: a.y, width: a.width, height: a.height, rx: 12, fill: a.color }));
            root.appendChild(svg("text", { x: a.x + 10, y: a.y + 22, class: "area-label" }, a.name));
        });

        const points = routePoints(data.zones, view.location, view.routeIds);
        if (view.routeIds && view.routeIds.length && points.length > 1) {
            root.appendChild(svg("polyline", { class: "route-line", points: points.map(function (p) { return p.join(","); }).join(" ") }));
        }

        const gate = data.zones.entrance;
        if (gate) {
            root.appendChild(svg("rect", { x: gate.x - 11, y: gate.y - 11, width: 22, height: 22, rx: 4, fill: "#546e7a" }));
            root.appendChild(svg("text", { x: gate.x, y: gate.y + 38, "text-anchor": "middle", class: "map-label" }, gate.name));
        }

        const visited = view.visited || [];
        const order = (view.routeIds || []).reduce(function (acc, id, i) { acc[id] = i + 1; return acc; }, {});

        data.animals.forEach(function (animal) {
            const pos = data.zones[animal.id];
            if (!pos) return;
            const isVisited = visited.indexOf(animal.id) !== -1;
            const classes = ["pin"];
            if (isVisited) classes.push("visited");
            if (view.recommended === animal.id) classes.push("recommended");
            if (view.selected === animal.id) classes.push("selected");

            const label = animal.name + (isVisited ? "（已參觀）" : "") + (order[animal.id] ? "，路線第 " + order[animal.id] + " 站" : "");
            const g = svg("g", { class: classes.join(" "), tabindex: 0, role: "button", "aria-label": label });
            if (view.recommended === animal.id) g.appendChild(svg("circle", { class: "pulse", cx: pos.x, cy: pos.y, r: 17 }));
            g.appendChild(svg("circle", { class: "ring", cx: pos.x, cy: pos.y, r: 23 }));
            g.appendChild(svg("circle", { class: "dot", cx: pos.x, cy: pos.y, r: 17 }));
            g.appendChild(svg("text", { x: pos.x, y: pos.y + 7, "text-anchor": "middle", "font-size": 20 }, isVisited ? "✓" : (EMOJI[animal.id] || "🐾")));
            g.appendChild(svg("text", { x: pos.x, y: pos.y + 42, "text-anchor": "middle", class: "map-label" }, animal.name));
            if (order[animal.id]) {
                g.appendChild(svg("text", { x: pos.x + 16, y: pos.y - 16, class: "map-label", "font-weight": "bold" }, "#" + order[animal.id]));
            }
            g.addEventListener("click", function () { onSelect(animal.id); });
            g.addEventListener("keydown", function (event) {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(animal.id);
                }
            });
            root.appendChild(g);
        });

        const here = data.zones[view.location];
        if (here) {
            root.appendChild(svg("circle", { class: "you", cx: here.x, cy: here.y, r: 28 }));
            root.appendChild(svg("text", { x: here.x, y: here.y - 34, "text-anchor": "middle", class: "you-label" }, "你在這裡"));
        }

        container.replaceChildren(root);
    }

    return { render: render, routePoints: routePoints };
})();

if (typeof module !== "undefined") module.exports = ZooMap;
