package main

import "core:fmt"
import "core:math"

Vec2 :: struct {
	x, y: f64,
}

Body :: struct {
	name:     string,
	position: Vec2,
	velocity: Vec2,
	mass:     f64,
}

add :: proc(a, b: Vec2) -> Vec2 {
	return Vec2{a.x + b.x, a.y + b.y}
}

scale :: proc(v: Vec2, factor: f64) -> Vec2 {
	return Vec2{v.x * factor, v.y * factor}
}

length_squared :: proc(v: Vec2) -> f64 {
	return v.x * v.x + v.y * v.y
}

// Compute all pairwise gravitational accelerations for a small 2D system.
accelerations :: proc(bodies: []Body, softening: f64) -> []Vec2 {
	result := make([]Vec2, len(bodies))
	for i in 0 ..< len(bodies) {
		for j in 0 ..< len(bodies) {
			if i == j {
				continue
			}
			delta := Vec2{
				bodies[j].position.x - bodies[i].position.x,
				bodies[j].position.y - bodies[i].position.y,
			}
			r2 := length_squared(delta) + softening*softening
			inv_r3 := 1.0 / (r2 * math.sqrt(r2))
			result[i] = add(result[i], scale(delta, bodies[j].mass*inv_r3))
		}
	}
	return result
}

step :: proc(bodies: []Body, dt, softening: f64) {
	a0 := accelerations(bodies, softening)
	for i in 0 ..< len(bodies) {
		bodies[i].velocity = add(bodies[i].velocity, scale(a0[i], 0.5*dt))
		bodies[i].position = add(bodies[i].position, scale(bodies[i].velocity, dt))
	}
	a1 := accelerations(bodies, softening)
	for i in 0 ..< len(bodies) {
		bodies[i].velocity = add(bodies[i].velocity, scale(a1[i], 0.5*dt))
	}
	delete(a0)
	delete(a1)
}

total_energy :: proc(bodies: []Body, softening: f64) -> f64 {
	energy := 0.0
	for i in 0 ..< len(bodies) {
		energy += 0.5 * bodies[i].mass * length_squared(bodies[i].velocity)
		for j in i+1 ..< len(bodies) {
			dx := bodies[j].position.x - bodies[i].position.x
			dy := bodies[j].position.y - bodies[i].position.y
			r := math.sqrt(dx*dx + dy*dy + softening*softening)
			energy -= bodies[i].mass * bodies[j].mass / r
		}
	}
	return energy
}

main :: proc() {
	softening := 0.01
	dt := 0.002
	steps := 2_000
	bodies := []Body{
		{"Aster", Vec2{-0.97000436, 0.24308753}, Vec2{0.466203685, 0.43236573}, 1.0},
		{"Beryl", Vec2{0.97000436, -0.24308753}, Vec2{0.466203685, 0.43236573}, 1.0},
		{"Cinder", Vec2{0.0, 0.0}, Vec2{-0.93240737, -0.86473146}, 1.0},
	}
	initial_energy := total_energy(bodies, softening)
	for _ in 0 ..< steps {
		step(bodies, dt, softening)
	}
	final_energy := total_energy(bodies, softening)

	fmt.println("Odin N-body simulation")
	fmt.printf("bodies: %d, steps: %d, dt: %.4f\n", len(bodies), steps, dt)
	fmt.printf("initial energy: %.9f\n", initial_energy)
	fmt.printf("final energy:   %.9f\n", final_energy)
	fmt.printf("energy drift:   %.3e\n", final_energy-initial_energy)
	for body in bodies {
		fmt.printf("%-8s position=(% .5f, % .5f) velocity=(% .5f, % .5f)\n",
			body.name, body.position.x, body.position.y, body.velocity.x, body.velocity.y)
	}
}
