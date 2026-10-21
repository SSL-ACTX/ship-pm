#!/usr/bin/env julia

"""
    julia ising.jl [--quick] [--size N] [--sweeps N] [--seed N]

Run a small, dependency-free 2D Ising model using the Metropolis algorithm.
Each temperature is simulated independently and may run on its own Julia thread.
Results are printed as CSV to stdout.
"""

using Random
using Printf
using Base.Threads

struct RunConfig
    side::Int
    sweeps::Int
    seed::UInt64
    temperatures::Vector{Float64}
end

function parse_args(args)
    side, sweeps, seed = 64, 1_000, UInt64(20261021)
    quick = false
    i = 1
    while i <= length(args)
        arg = args[i]
        if arg == "--quick"
            quick = true
        elseif arg in ("--size", "--sweeps", "--seed")
            i == length(args) && error("$arg requires a value")
            value = parse(Int, args[i + 1])
            value > 0 || error("$arg must be positive")
            arg == "--size" && (side = value)
            arg == "--sweeps" && (sweeps = value)
            arg == "--seed" && (seed = UInt64(value))
            i += 1
        else
            error("Unknown option: $arg\nRun with --quick or --size N --sweeps N --seed N")
        end
        i += 1
    end
    quick && ((side, sweeps) = (min(side, 16), min(sweeps, 80)))
    side >= 2 || error("--size must be at least 2")
    return RunConfig(side, sweeps, seed, [1.5, 2.0, 2.269, 2.5, 3.0])
end

@inline function magnetization(spins::Matrix{Int8})
    return sum(spins)
end

function total_energy(spins::Matrix{Int8})
    side = size(spins, 1)
    energy = 0
    @inbounds for y in 1:side, x in 1:side
        s = spins[y, x]
        energy -= s * (spins[y, mod1(x + 1, side)] + spins[mod1(y + 1, side), x])
    end
    return energy
end

@inline function flip_delta(spins::Matrix{Int8}, x::Int, y::Int)
    side = size(spins, 1)
    neighbors = spins[y, mod1(x - 1, side)] + spins[y, mod1(x + 1, side)] +
                spins[mod1(y - 1, side), x] + spins[mod1(y + 1, side), x]
    return 2 * spins[y, x] * neighbors
end

function simulate_temperature(cfg::RunConfig, temperature::Float64, temperature_index::Int)
    rng = MersenneTwister(cfg.seed + UInt64(temperature_index))
    spins = rand(rng, Int8[-1, 1], cfg.side, cfg.side)
    sites = cfg.side * cfg.side
    burn_in = max(1, cfg.sweeps ÷ 5)
    energy_sum = 0.0
    energy_sq_sum = 0.0
    magnetization_sum = 0.0
    measurements = 0

    # Precompute Boltzmann acceptance probabilities for the four possible ΔE values.
    acceptance = ntuple(k -> exp(-4.0 * (k - 1) / temperature), 5)
    @inbounds for sweep in 1:cfg.sweeps
        for _ in 1:sites
            x, y = rand(rng, 1:cfg.side), rand(rng, 1:cfg.side)
            delta = flip_delta(spins, x, y)
            if delta <= 0 || rand(rng) < acceptance[delta ÷ 4 + 1]
                spins[y, x] = -spins[y, x]
            end
        end
        if sweep > burn_in && sweep % 5 == 0
            energy = total_energy(spins) / sites
            magnetization_per_site = abs(magnetization(spins)) / sites
            energy_sum += energy
            energy_sq_sum += energy * energy
            magnetization_sum += magnetization_per_site
            measurements += 1
        end
    end

    mean_energy = energy_sum / measurements
    heat_capacity = sites * (energy_sq_sum / measurements - mean_energy^2) / temperature^2
    mean_abs_magnetization = magnetization_sum / measurements
    return (temperature=temperature, energy=mean_energy,
            abs_magnetization=mean_abs_magnetization, heat_capacity=heat_capacity,
            measurements=measurements)
end

function run(cfg::RunConfig)
    results = Vector{NamedTuple}(undef, length(cfg.temperatures))
    @threads for i in eachindex(cfg.temperatures)
        results[i] = simulate_temperature(cfg, cfg.temperatures[i], i)
    end
    return results
end

function main(args)
    cfg = parse_args(args)
    @printf("# 2D Ising model: %d×%d lattice, %d sweeps, %d Julia thread(s)\n",
            cfg.side, cfg.side, cfg.sweeps, nthreads())
    println("temperature,mean_energy_per_spin,mean_abs_magnetization,heat_capacity,measurements")
    for row in run(cfg)
        @printf("%.3f,%.6f,%.6f,%.6f,%d\n", row.temperature, row.energy,
                row.abs_magnetization, row.heat_capacity, row.measurements)
    end
end

if abspath(PROGRAM_FILE) == @__FILE__
    main(ARGS)
end
